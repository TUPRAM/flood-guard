"""The AIT/MBRSC guard of planning protocol v1a (guardrail GR9; plan 2.3 item 9; plan row 8.1 A1).

"A pre-commit test must fail if any committed script reads AIT-VAP001 or MBRSC paths without a recorded grant
receipt. No AIT or MBRSC number appears in committed code or on any public surface." These tests run the guard
on the checkout, and on invented files to show what it refuses. No product file is opened.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from floodguard import ait_mbrsc_guard as guard
from floodguard import rights

ROOT = Path(__file__).resolve().parents[1]

AIT_PATH_LINE = 'layer = read(external / "reference_candidates/sentinel_asia_ait/AIT-VAP001-TH-extracted/AIT-VAP001-TH.shp")'
MBRSC_PATH_LINE = 'layer = read("zip://" + external + "MBRSC_THAILAND_FLOOD-MAP-SHP.zip")'
FOLDER_LINE = 'folder = external / "sentinel_asia"'


def _write(root: Path, name: str, text: str) -> str:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return name


def _kinds(findings: list[guard.Finding]) -> list[tuple[str, str, tuple[str, ...]]]:
    return [(finding.path, finding.kind, finding.products) for finding in findings]


# --- The checkout ----------------------------------------------------------------------------------------


def test_the_checkout_passes_the_guard_and_no_grant_is_recorded() -> None:
    summary = guard.check(ROOT)
    assert summary["findings"] == [] and summary["passed"] is True
    assert summary["grants_recorded"] == {}, "no rights record grants the AIT or the MBRSC product today"
    assert summary["code_files_searched"] > 500 and summary["legacy_files_in_the_baseline"] >= 20


def test_the_baseline_lists_legacy_files_and_says_it_is_not_a_grant() -> None:
    document = json.loads((ROOT / guard.BASELINE_PATH).read_text(encoding="ascii"))
    assert document["schema"] == guard.BASELINE_SCHEMA and "GR9_ait_mbrsc_guard" in document["guardrail"]
    assert document["what_this_is_not"].startswith("Not a grant.")
    assert "A1-OP7" in document["grant"] and document["grant_sources"] == dict(guard.GRANT_SOURCES)
    baseline = guard.load_baseline(ROOT)
    files = set(guard.repository_files(ROOT))
    for name, entry in baseline.items():
        assert name in files, f"{name} is in the baseline and not in the repository"
        assert Path(name).suffix in guard.CODE_SUFFIXES
        naming = guard.naming_lines((ROOT / name).read_text(encoding="utf-8"))
        assert guard.lines_digest(naming) == entry["naming_lines_sha256"], name
        assert sorted(naming) == entry["products"], name
    # The earlier AIT inspection code, which the plan keeps unchanged, is legacy; no file of this task is.
    assert "scripts/inspect_ait_reference_candidate.py" in baseline and "src/floodguard/ait_reference_candidate.py" in baseline
    assert not [name for name in baseline if name.startswith("scripts/diagnostics/") or "diagnosis" in name]
    assert guard.GUARD_FILES.isdisjoint(baseline) and all((ROOT / name).is_file() for name in guard.GUARD_FILES)


def test_no_diagnosis_script_names_either_product() -> None:
    scripts = sorted((ROOT / "scripts" / "diagnostics").glob("*.py"))
    assert len(scripts) >= 7
    for path in scripts:
        assert guard.naming_lines(path.read_text(encoding="utf-8")) == {}, path.name
    for module in ("abstention_diagnosis.py", "diagnosis_run.py", "diagnosis_layers.py"):
        assert guard.naming_lines((ROOT / "src" / "floodguard" / module).read_text(encoding="utf-8")) == {}, module


# --- What the guard refuses ------------------------------------------------------------------------------


def test_a_new_script_that_names_a_product_path_fails(tmp_path: Path) -> None:
    files = [
        _write(tmp_path, "scripts/diagnostics/new_ait.py", AIT_PATH_LINE + "\n"),
        _write(tmp_path, "scripts/new_mbrsc.py", "import os\n" + MBRSC_PATH_LINE + "\n"),
        _write(tmp_path, "src/floodguard/new_folder.py", FOLDER_LINE + "\n"),
        _write(tmp_path, "apps/web/scripts/new.mjs", 'const id = "AIT_VAP001";\n'),
        _write(tmp_path, "scripts/clean.py", "print('nothing to see')\n"),
    ]
    findings = guard.path_findings(tmp_path, files, baseline={}, grants={})
    assert _kinds(findings) == [
        ("apps/web/scripts/new.mjs", "names_a_product_without_a_grant", ("ait",)),
        ("scripts/diagnostics/new_ait.py", "names_a_product_without_a_grant", ("ait",)),
        ("scripts/new_mbrsc.py", "names_a_product_without_a_grant", ("mbrsc",)),
        ("src/floodguard/new_folder.py", "names_a_product_without_a_grant", ("ait", "mbrsc")),
    ]
    assert "no grant is recorded" in findings[0].describe()


def test_a_sentence_about_the_products_and_the_name_of_the_guard_are_not_a_path(tmp_path: Path) -> None:
    text = (
        '"""Figures computed against AIT or MBRSC products are not recorded here (guardrail GR9_ait_mbrsc_guard)."""\n'
        "from floodguard import ait_mbrsc_guard\n"
        "WAIT = 'maintain the bait'\n"
    )
    assert guard.naming_lines(text) == {}
    assert guard.path_findings(tmp_path, [_write(tmp_path, "scripts/prose.py", text)], baseline={}, grants={}) == []


def test_only_code_files_are_searched_for_paths(tmp_path: Path) -> None:
    files = [_write(tmp_path, "docs/note.md", AIT_PATH_LINE + "\n"), _write(tmp_path, "outputs/record.json", json.dumps({"p": "AIT-VAP001"})),
             _write(tmp_path, "notebooks/explore.ipynb", json.dumps({"cells": [{"source": [MBRSC_PATH_LINE]}]}))]
    assert guard.code_files(files) == ["notebooks/explore.ipynb"]
    assert _kinds(guard.path_findings(tmp_path, files, baseline={}, grants={})) == [
        ("notebooks/explore.ipynb", "names_a_product_without_a_grant", ("mbrsc",))]


def test_a_legacy_file_passes_until_a_line_that_names_a_product_changes(tmp_path: Path) -> None:
    name = _write(tmp_path, "scripts/legacy.py", "import json\n" + AIT_PATH_LINE + "\nprint(1)\n")
    naming = guard.naming_lines((tmp_path / name).read_text(encoding="utf-8"))
    baseline = {name: {"products": ["ait"], "naming_lines": 1, "naming_lines_sha256": guard.lines_digest(naming)}}
    assert guard.path_findings(tmp_path, [name], baseline, grants={}) == []
    # Another line may change; the file stays legacy.
    _write(tmp_path, "scripts/legacy.py", "import json\nimport os\n" + AIT_PATH_LINE + "\nprint(2)\n")
    assert guard.path_findings(tmp_path, [name], baseline, grants={}) == []
    # A new line that names a product does not.
    _write(tmp_path, "scripts/legacy.py", "import json\n" + AIT_PATH_LINE + "\n" + MBRSC_PATH_LINE + "\n")
    assert _kinds(guard.path_findings(tmp_path, [name], baseline, grants={})) == [("scripts/legacy.py", "legacy_file_changed", ("ait", "mbrsc"))]
    # The guard's own files are not searched.
    own = _write(tmp_path, "src/floodguard/ait_mbrsc_guard.py", AIT_PATH_LINE + "\n")
    assert guard.path_findings(tmp_path, [own], baseline={}, grants={}) == []


def _grant_record(**changes: object) -> dict:
    record = {
        "schema": "floodguard.rights_basis_grant.invented.v1", "record_id": "invented_grant", "record_status": "confirmed",
        "signed_by_human": True, "human_rights_clearance": True,
        "owner_confirmation": {"status": "confirmed", "required_from": ["Putu", "Rachmania"], "confirmed_by": ["Putu", "Rachmania"],
                               "confirmed_on": "2026-10-05"},
        "required_attribution_text": "an invented provider", "licence": {"name": "an invented grant"},
        "official_warning": False, "can_feed_decision_layer": False,
    }
    record.update(changes)
    return record


def test_a_recorded_grant_lifts_the_refusal_for_its_own_product_only(tmp_path: Path) -> None:
    files = [_write(tmp_path, "scripts/a.py", AIT_PATH_LINE + "\n"), _write(tmp_path, "scripts/m.py", MBRSC_PATH_LINE + "\n")]
    _write(tmp_path, "docs/grant.json", json.dumps(_grant_record()))
    records = (rights.RegisteredRecord("invented_ait_grant", "docs/grant.json", "an invented grant of the AIT product", guard.GRANT_SOURCES[guard.AIT]),)
    registry = rights.RightsRegistry(tmp_path, records)
    grants = guard.recorded_grants(registry, records)
    assert grants == {"ait": "docs/grant.json"}
    assert _kinds(guard.path_findings(tmp_path, files, baseline={}, grants=grants)) == [("scripts/m.py", "names_a_product_without_a_grant", ("mbrsc",))]
    # A record that is registered and not confirmed, or not signed by a human, is not a grant.
    for changes in ({"record_status": "draft"}, {"signed_by_human": False},
                    {"owner_confirmation": {"status": "confirmed", "required_from": ["Putu", "Rachmania"], "confirmed_by": ["Putu"]}}):
        _write(tmp_path, "docs/grant.json", json.dumps(_grant_record(**changes)))
        assert guard.recorded_grants(registry, records) == {}, changes
    # A record of another source grants neither product, and a registered record whose file is missing grants nothing.
    other = (rights.RegisteredRecord("invented", "docs/grant.json", "something else", rights.SOURCE_SENTINEL1),)
    _write(tmp_path, "docs/grant.json", json.dumps(_grant_record()))
    assert guard.recorded_grants(rights.RightsRegistry(tmp_path, other), other) == {}
    missing = (rights.RegisteredRecord("invented_ait_grant", "docs/absent.json", "absent", guard.GRANT_SOURCES[guard.AIT]),)
    assert guard.recorded_grants(rights.RightsRegistry(tmp_path, missing), missing) == {}


def test_the_registry_of_the_repository_holds_no_record_of_either_source() -> None:
    sources = {entry.source for entry in rights.REGISTERED_RECORDS}
    assert sources.isdisjoint(guard.GRANT_SOURCES.values())
    assert set(guard.GRANT_SOURCES) == {"ait", "mbrsc"}


# --- Numbers ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("line", [
    "Figures computed against AIT or MBRSC products were also seen and are not recorded here (EK-07).",
    "Guardrail GR9: no AIT or MBRSC number in committed code (plan 2.3 item 9, plan 0 item 3).",
    "The AIT-VAP001-TH extent of 14 Sep 2024 (ALOS-2) is not processed until it is granted; see A1-OP7 and v1a.",
    "No rights record grants the AIT product; the SHA-256 of each naming line is in the baseline.",
    "The separation against the season envelope is 0.421.",  # A figure, and no product name.
])
def test_identifiers_and_dates_beside_a_product_name_are_not_figures(line: str) -> None:
    assert guard.figure_in_line(line) is False, line


@pytest.mark.parametrize("line", [
    "Darkening AUC against the AIT extent: 0.512",
    "MBRSC overlap 3.2 km2",
    "| AIT 14 Sep | 41% of the cells |",
    "agreement with MBRSC was 7 of 10",
])
def test_a_figure_beside_a_product_name_is_refused(line: str) -> None:
    assert guard.figure_in_line(line) is True, line


def test_number_findings_cover_the_files_of_the_diagnosis_only(tmp_path: Path) -> None:
    bad = "The darkening separates the AIT extent with 0.512.\n"
    files = [
        _write(tmp_path, "docs/proposal_execution/automated_track/WHY_THRESHOLD_ONLY_FAILED.md", "A clean line.\n" + bad),
        _write(tmp_path, "outputs/a1_diagnosis/figure.json", json.dumps({"note": "MBRSC overlap 3.2 km2"}, indent=2) + "\n"),
        _write(tmp_path, "outputs/planning_v1/a1_diagnosis_figure.json", json.dumps({"note": "nothing about either product: 0.5"}) + "\n"),
        _write(tmp_path, "scripts/diagnostics/figure.py", "# AIT-VAP001 is not read here (guardrail GR9).\n"),
        _write(tmp_path, "docs/elsewhere.md", bad),
    ]
    findings = guard.number_findings(tmp_path, files)
    assert [(finding.path, finding.kind, finding.products) for finding in findings] == [
        ("docs/proposal_execution/automated_track/WHY_THRESHOLD_ONLY_FAILED.md", "figure_beside_a_product_name", ("ait",)),
        ("outputs/a1_diagnosis/figure.json", "figure_beside_a_product_name", ("mbrsc",)),
    ]
    assert "line 2" in findings[0].detail


def test_the_files_of_the_diagnosis_hold_no_figure_beside_either_name() -> None:
    files = guard.repository_files(ROOT)
    covered = [name for name in files if any(Path(name).match(pattern) for pattern in guard.A1_FILE_PATTERNS)]
    assert "docs/proposal_execution/automated_track/WHY_THRESHOLD_ONLY_FAILED.md" in covered
    assert len([name for name in covered if name.startswith("scripts/diagnostics/")]) >= 7
    assert guard.number_findings(ROOT, files) == []


# --- The command -----------------------------------------------------------------------------------------


def test_the_command_passes_on_the_checkout_and_does_not_replace_the_baseline(capsys: pytest.CaptureFixture[str]) -> None:
    spec = importlib.util.spec_from_file_location("check_ait_mbrsc_guard", ROOT / "scripts" / "check_ait_mbrsc_guard.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    before = (ROOT / guard.BASELINE_PATH).read_bytes()
    assert module.main([]) == 0
    assert json.loads(capsys.readouterr().out)["passed"] is True
    assert module.main(["--write-baseline"]) == 2
    assert (ROOT / guard.BASELINE_PATH).read_bytes() == before


def test_a_missing_or_malformed_baseline_is_refused(tmp_path: Path) -> None:
    with pytest.raises(guard.GuardError, match="missing"):
        guard.load_baseline(tmp_path)
    _write(tmp_path, guard.BASELINE_PATH.as_posix(), json.dumps({"schema": "other", "files": {}}))
    with pytest.raises(guard.GuardError, match="schema"):
        guard.load_baseline(tmp_path)
    _write(tmp_path, guard.BASELINE_PATH.as_posix(), json.dumps({"schema": guard.BASELINE_SCHEMA, "files": {"a.py": {"products": ["ait"]}}}))
    with pytest.raises(guard.GuardError, match="a.py"):
        guard.load_baseline(tmp_path)
