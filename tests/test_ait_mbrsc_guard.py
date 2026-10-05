"""The AIT/MBRSC guard of planning protocol v1a (guardrail GR9; plan 2.3 item 9; plan row 8.1 A1).

"A pre-commit test must fail if any committed script reads AIT-VAP001 or MBRSC paths without a recorded grant
receipt. No AIT or MBRSC number appears in committed code or on any public surface." These tests run the guard
on the checkout, and on invented files to show what it refuses and what it does not see. No product file is
opened.
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
    assert summary["legacy_files_bound_by_their_definitions"] >= 10
    assert "floodguard.public_reference_files" in summary["legacy_reader_modules"]


def test_the_baseline_lists_legacy_files_and_says_it_is_not_a_grant() -> None:
    document = json.loads((ROOT / guard.BASELINE_PATH).read_text(encoding="ascii"))
    assert document["schema"] == guard.BASELINE_SCHEMA and "GR9_ait_mbrsc_guard" in document["guardrail"]
    assert document["what_this_is_not"].startswith("Not a grant, and not a proof")
    assert "ait_mbrsc_guard_baseline_v1.json" in document["replaces"]
    assert "A1-OP7" in document["grant"] and document["grant_sources"] == dict(guard.GRANT_SOURCES)
    baseline = guard.load_baseline(ROOT)
    readers = guard.reader_modules_of(document)
    files = set(guard.repository_files(ROOT))
    for name, entry in baseline.items():
        assert name in files, f"{name} is in the baseline and not in the repository"
        assert Path(name).suffix in guard.CODE_SUFFIXES
        text = (ROOT / name).read_text(encoding="utf-8")
        naming = guard.naming_lines(text, Path(name).suffix, readers)
        assert guard.lines_digest(naming) == entry["naming_lines_sha256"], name
        assert sorted(naming) == entry["products"], name
        # A legacy Python file under scripts/ or src/ is also bound by its functions and classes; no other file is.
        assert ("definitions_sha256" in entry) == guard.is_definition_bound(name), name
        if guard.is_definition_bound(name):
            assert guard.definitions_digest(guard.definitions(text)) == entry["definitions_sha256"], name
    # The earlier AIT inspection code, which the plan keeps unchanged, is legacy; no file of this task is.
    assert "scripts/inspect_ait_reference_candidate.py" in baseline and "src/floodguard/ait_reference_candidate.py" in baseline
    assert not [name for name in baseline if name.startswith("scripts/diagnostics/") or "diagnosis" in name]
    assert guard.GUARD_FILES.isdisjoint(baseline) and all((ROOT / name).is_file() for name in guard.GUARD_FILES)
    # A reader module is a legacy module, and the file that imports it is listed as well.
    for module in readers:
        assert f"src/{module.replace('.', '/')}.py" in baseline
    assert "scripts/review_sentinel_asia_geometry_quality.py" in baseline
    assert not (ROOT / "docs" / "proposal_execution" / "ait_mbrsc_guard_baseline_v1.json").exists()


def test_no_diagnosis_script_names_either_product() -> None:
    scripts = sorted((ROOT / "scripts" / "diagnostics").glob("*.py"))
    assert len(scripts) >= 7
    readers = guard.reader_modules_of(guard.read_baseline(ROOT))
    for path in scripts:
        assert guard.naming_lines(path.read_text(encoding="utf-8"), ".py", readers) == {}, path.name
    for module in ("abstention_diagnosis.py", "diagnosis_run.py", "diagnosis_layers.py"):
        assert guard.naming_lines((ROOT / "src" / "floodguard" / module).read_text(encoding="utf-8"), ".py", readers) == {}, module


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


@pytest.mark.parametrize(("name", "text", "products"), [
    # A script that takes the layers from another file and only labels them, as the exploratory scripts did.
    ("scripts/labels.py", "for nm, lab in [('AIT ALOS-2 14Sep', ait), ('MBRSC S1 15Sep', mb), ('UNOSAT cum Aug-Oct', un)]:\n    pass\n",
     ("ait", "mbrsc")),
    ("scripts/identifier.py", "ait_mask = load(first)\nflooded = dom & ait_mask\n", ("ait",)),
    ("scripts/camel.py", "mbrscLayer = load(second)\n", ("mbrsc",)),
    # A name used only inside an f-string, in a line too long to be a label.
    ("scripts/fstring.py", "print(f'area {flooded.sum() * px:.3f} km2 and overlap {(flooded & ait).sum() * px:.3f} km2 of the frame in this run, "
                           "as the practice gives it')\n", ("ait",)),
    # The product folder alone, a bare folder name and a bare file name.
    ("scripts/folder.py", 'for path in (external / "reference_candidates").rglob("*.shp"):\n    read(path)\n', ("ait",)),
    ("scripts/part.py", 'layer = read(external / "mbrsc" / "flood.shp")\n', ("mbrsc",)),
    ("scripts/archive.py", 'layer = read(folder / "MBRSC.zip")\n', ("mbrsc",)),
    # Other languages and configuration files.
    ("analysis/overlap.R", 'ait <- st_read(file.path(root, "extent.shp"))\n', ("ait",)),
    ("apps/web/src/view.jsx", 'const layer = load("mbrsc");\n', ("mbrsc",)),
    ("config/layers.yml", "flood_layer: external/mbrsc/flood.shp\n", ("mbrsc",)),
    ("config/layers.yaml", 'label: "AIT extent"\n', ("ait",)),
    ("config/paths.toml", 'ait_extent = "extent.shp"\n', ("ait",)),
    ("tools/run.cmd", "python overlap.py --layer mbrsc\n", ("mbrsc",)),
])
def test_a_bare_product_word_in_an_identifier_or_a_short_string_is_a_name(tmp_path: Path, name: str, text: str, products: tuple[str, ...]) -> None:
    files = [_write(tmp_path, name, text)]
    assert _kinds(guard.path_findings(tmp_path, files, baseline={}, grants={})) == [(name, "names_a_product_without_a_grant", products)]


def test_a_sentence_about_the_products_and_the_name_of_the_guard_are_not_a_path(tmp_path: Path) -> None:
    text = (
        '"""Figures computed against AIT or MBRSC products are not recorded here (guardrail GR9_ait_mbrsc_guard)."""\n'
        "from floodguard import ait_mbrsc_guard\n"
        "WAIT = 'maintain the bait'\n"
        "# The AIT extent is not read here.\n"
        "NOTE = ('The guardrail forbids any number of the AIT or the MBRSC product in committed code, and this module '\n"
        "        'holds none.')\n"
        'keys = receipt["reference_candidates"]\n'
    )
    assert guard.naming_lines(text) == {}
    assert guard.path_findings(tmp_path, [_write(tmp_path, "scripts/prose.py", text)], baseline={}, grants={}) == []
    # The same holds in another language: a comment line and a long sentence are prose.
    script = "// The AIT extent is not read here.\nconst note = 'No number of the AIT or the MBRSC product is shown on this page, by rule.';\n"
    assert guard.path_findings(tmp_path, [_write(tmp_path, "apps/web/src/note.ts", script)], baseline={}, grants={}) == []


def test_only_code_files_are_searched_for_paths(tmp_path: Path) -> None:
    files = [_write(tmp_path, "docs/note.md", AIT_PATH_LINE + "\n"), _write(tmp_path, "outputs/record.json", json.dumps({"p": "AIT-VAP001"})),
             _write(tmp_path, "notebooks/explore.ipynb", json.dumps({"cells": [{"source": [MBRSC_PATH_LINE]}]}))]
    assert guard.code_files(files) == ["notebooks/explore.ipynb"]
    assert _kinds(guard.path_findings(tmp_path, files, baseline={}, grants={})) == [
        ("notebooks/explore.ipynb", "names_a_product_without_a_grant", ("mbrsc",))]
    assert {".r", ".jsx", ".yml", ".yaml", ".toml", ".cmd"} <= guard.CODE_SUFFIXES
    assert guard.code_files(["analysis/overlap.R", "data/table.csv", "data/manifest.json"]) == ["analysis/overlap.R"]


def test_the_outputs_of_a_notebook_are_not_searched(tmp_path: Path) -> None:
    notebook = {"cells": [
        {"cell_type": "code", "source": ["x = 1\n"], "outputs": [{"data": {"image/png": "iVBOR+AIT/mbrsc+0KGgo="}}]},
        {"cell_type": "markdown", "source": ["The AIT extent is blocked."]},
    ]}
    name = _write(tmp_path, "notebooks/plot.ipynb", json.dumps(notebook))
    assert guard.path_findings(tmp_path, [name], baseline={}, grants={}) == []
    notebook["cells"].append({"cell_type": "code", "source": ["ait = read(first)\n"]})
    _write(tmp_path, "notebooks/plot.ipynb", json.dumps(notebook))
    assert _kinds(guard.path_findings(tmp_path, [name], baseline={}, grants={})) == [(name, "names_a_product_without_a_grant", ("ait",))]


def test_what_the_guard_does_not_see(tmp_path: Path) -> None:
    """The limits the write-up states (open point A1-OP11): each of these reads a product and passes."""

    files = [
        _write(tmp_path, "scripts/manifest.py", "import json\nfor row in json.load(open('layers.json')):\n    read(row['path'])\n"),
        _write(tmp_path, "scripts/split.py", "name = 'MBR' + 'SC'\nread(folder / (name + '.zip'))\n"),
        _write(tmp_path, "data/layers.json", json.dumps([{"path": "sentinel_asia/MBRSC_THAILAND_FLOOD-MAP-SHP.zip"}])),
        _write(tmp_path, "data/layers.csv", "path\nreference_candidates/sentinel_asia_ait/AIT-VAP001-TH.shp\n"),
    ]
    assert guard.path_findings(tmp_path, files, baseline={}, grants={}) == []


def _legacy_entry(tmp_path: Path, name: str, readers: dict[str, list[str]] | None = None) -> dict:
    text = (tmp_path / name).read_text(encoding="utf-8")
    naming = guard.naming_lines(text, Path(name).suffix, readers)
    entry: dict = {"products": sorted(naming), "naming_lines": 1, "naming_lines_sha256": guard.lines_digest(naming)}
    if guard.is_definition_bound(name):
        entry["definitions_sha256"] = guard.definitions_digest(guard.definitions(text))
    return entry


def test_a_legacy_file_passes_until_a_line_that_names_a_product_changes(tmp_path: Path) -> None:
    name = _write(tmp_path, "tests/test_legacy.py", "import json\n" + AIT_PATH_LINE + "\nprint(1)\n")
    baseline = {name: _legacy_entry(tmp_path, name)}
    assert "definitions_sha256" not in baseline[name], "a legacy test is bound by its naming lines only"
    assert guard.path_findings(tmp_path, [name], baseline, grants={}) == []
    # Another line may change, and a test may be added; the file stays legacy.
    _write(tmp_path, name, "import json\nimport os\n" + AIT_PATH_LINE + "\nprint(2)\n\n\ndef test_more():\n    pass\n")
    assert guard.path_findings(tmp_path, [name], baseline, grants={}) == []
    # A new line that names a product does not.
    _write(tmp_path, name, "import json\n" + AIT_PATH_LINE + "\n" + MBRSC_PATH_LINE + "\n")
    assert _kinds(guard.path_findings(tmp_path, [name], baseline, grants={})) == [(name, "legacy_file_changed", ("ait", "mbrsc"))]
    # The guard's own files are not searched.
    own = _write(tmp_path, "src/floodguard/ait_mbrsc_guard.py", AIT_PATH_LINE + "\n")
    assert guard.path_findings(tmp_path, [own], baseline={}, grants={}) == []


def test_a_legacy_script_fails_when_it_gains_a_function(tmp_path: Path) -> None:
    source = "ZIP = folder / 'sentinel_asia' / 'archive.zip'\n\n\ndef review():\n    return inspect(ZIP)\n"
    name = _write(tmp_path, "scripts/review_legacy.py", source)
    baseline = {name: _legacy_entry(tmp_path, name)}
    assert guard.is_definition_bound(name) and guard.path_findings(tmp_path, [name], baseline, grants={}) == []
    # New processing code that uses the path the file already names: no naming line changes, and the guard still fails.
    _write(tmp_path, name, source + "\n\ndef overlap(candidate):\n    return intersect(read(ZIP), candidate)\n")
    assert _kinds(guard.path_findings(tmp_path, [name], baseline, grants={})) == [
        (name, "legacy_file_gained_or_lost_a_definition", ("ait", "mbrsc"))]
    # A change inside an existing function is not seen: the write-up says so.
    _write(tmp_path, name, source.replace("return inspect(ZIP)", "return intersect(read(ZIP), other)"))
    assert guard.path_findings(tmp_path, [name], baseline, grants={}) == []
    assert guard.definitions("class A:\n    def b(self):\n        def c():\n            pass\n") == ["A", "A.b", "A.b.c"]
    assert guard.definitions("def broken(:\n") is None
    assert not guard.is_definition_bound("tests/test_x.py") and not guard.is_definition_bound("apps/web/scripts/build.py")


def test_a_file_that_imports_a_legacy_reader_module_names_its_products(tmp_path: Path) -> None:
    readers = {"floodguard.public_reference_files": ["ait", "mbrsc"]}
    files = [
        _write(tmp_path, "scripts/new_reader.py", "from floodguard.public_reference_files import inspect_zip\nprint(inspect_zip)\n"),
        _write(tmp_path, "scripts/new_reader_2.py", "from floodguard import (\n    scoring,\n    public_reference_files,\n)\n"),
        _write(tmp_path, "scripts/new_reader_3.py", "import floodguard.public_reference_files as files\n"),
        _write(tmp_path, "scripts/other.py", "from floodguard import scoring\nfrom floodguard.public_reference_inventory import rows\n"),
    ]
    assert _kinds(guard.path_findings(tmp_path, files, baseline={}, grants={}, reader_modules=readers)) == [
        (name, "names_a_product_without_a_grant", ("ait", "mbrsc"))
        for name in ("scripts/new_reader.py", "scripts/new_reader_2.py", "scripts/new_reader_3.py")]
    assert guard.path_findings(tmp_path, files, baseline={}, grants={}) == [], "without the list of reader modules an import names nothing"
    assert guard.module_name("src/floodguard/label_factory/rights_clearance.py") == "floodguard.label_factory.rights_clearance"
    assert guard.module_name("scripts/x.py") is None


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
    "The AIT-VAP001-TH extent of 14 Sep (ALOS-2) is not processed until it is granted; see A1-OP7 and v1a.",
    "No rights record grants the AIT product; the SHA-256 of each naming line is in the baseline.",
    "The guard is in `src/floodguard/ait_mbrsc_guard.py`; 29 legacy files are in its baseline.",  # The guard's name is no product name.
    "The separation against the season envelope is 0.421.",  # A figure, and no product name.
])
def test_identifiers_and_dates_beside_a_product_name_are_not_figures(line: str) -> None:
    assert guard.figure_in_line(line) is False, line


@pytest.mark.parametrize("line", [
    "Darkening AUC against the AIT extent: 0.512",
    "MBRSC overlap 3.2 km2",
    "| AIT 14 Sep | 41% of the cells |",
    "agreement with MBRSC was 7 of 10",
    "MBRSC overlap 2031 cells",  # Not a year.
    "The AIT extent of 14 Sep 2024",  # A year is a figure in these files.
    "AIT row 0.512",
    "AIT agreement 41 marked cells",  # Not a day and a month.
    '"auc_vs_ait_extent": 0.512,',
    "mbrsc_overlap_km2 = 3.2",
])
def test_a_figure_beside_a_product_name_is_refused(line: str) -> None:
    assert guard.figure_in_line(line) is True, line


def test_a_number_under_or_beside_a_product_name_in_json_is_refused() -> None:
    assert guard.json_findings({"against_the_AIT_extent": {"auc": 0.512}}) == [
        "$.against_the_AIT_extent: a number under a key that names a product"]
    assert guard.json_findings({"figures": {"auc_vs_ait_extent": 0.512, "mbrsc_overlap_km2": 3.2}}) == [
        "$.figures.auc_vs_ait_extent: a number under a key that names a product",
        "$.figures.mbrsc_overlap_km2: a number under a key that names a product"]
    assert guard.json_findings({"rows": [{"layer": "the AIT extent", "auc": 0.512, "ok": True}]}) == [
        "$.rows[0].auc: a number beside the string at $.rows[0].layer, which names a product"]
    assert guard.json_findings(["MBRSC", 3.2]) == ["$[1]: a number beside a string that names a product"]
    assert guard.json_findings({"note": "The overlap with the MBRSC map was 3.2 km2. Nothing else."}) == [
        "$.note: a figure in the sentence that names a product"]
    # Nothing to refuse: a number elsewhere, a product named with no number, and the guard's own name.
    clean = {"auc": 0.421, "open_points": [{"id": "A1-OP7", "point": "What a grant receipt for the AIT or MBRSC product is."}],
             "not_computed": ["any figure against the AIT or MBRSC products"], "guardrail": "GR9_ait_mbrsc_guard", "legacy_files": 29,
             "note": "No AIT figure is recorded. The gate is 0.72."}
    assert guard.json_findings(clean) == []


def test_a_figure_in_the_sentence_or_the_table_column_of_a_product_name_is_refused() -> None:
    wrapped = "The darkening separates the AIT extent\nwith a value of 0.512, as seen.\n\nThe gate is 0.72.\n"
    assert guard.text_findings(wrapped) == [(1, "The darkening separates the AIT extent with a value of 0.512, as seen.")]
    table = "| Layer | Season envelope | MBRSC map |\n|---|---:|---:|\n| Darkening | 0.421 | 0.512 |\n| Terrain | 0.680 | not computed |\n"
    assert guard.text_findings(table) == [(3, "| Darkening | 0.421 | 0.512 |")]
    clean = ("Figures against the AIT or MBRSC products were seen\nin the exploratory phase (EK-07). The gate is 0.72.\n\n"
             "| Layer | Value |\n|---|---:|\n| Season envelope | 0.421 |\n")
    assert guard.text_findings(clean) == []


def test_number_findings_cover_the_files_of_the_diagnosis_only(tmp_path: Path) -> None:
    bad = "The darkening separates the AIT extent with 0.512.\n"
    heading = guard.A1_SECTIONS["outputs/planning_v1/README.md"]
    files = [
        _write(tmp_path, "docs/proposal_execution/automated_track/WHY_THRESHOLD_ONLY_FAILED.md", "A clean line.\n" + bad),
        _write(tmp_path, "outputs/a1_diagnosis/figure.json", json.dumps({"note": "MBRSC overlap 3.2 km2"}, indent=2) + "\n"),
        _write(tmp_path, "outputs/a1_diagnosis/nested.json", json.dumps({"against_the_AIT_extent": {"auc": 0.512}}, indent=2) + "\n"),
        _write(tmp_path, "outputs/planning_v1/a1_diagnosis_figure.json", json.dumps({"note": "nothing about either product: 0.5"}) + "\n"),
        _write(tmp_path, "outputs/planning_v1/README.md", "AIT 0.3 in another task's section.\n\n" + heading + "\n\nAIT 0.5\n"),
        _write(tmp_path, "scripts/diagnostics/figure.py", "# AIT-VAP001 is not read here (guardrail GR9).\n"),
        _write(tmp_path, "tests/test_a1_diagnosis_outputs.py", "MBRSC_OVERLAP = 3.2\n"),
        _write(tmp_path, "docs/elsewhere.md", bad),
    ]
    findings = guard.number_findings(tmp_path, files)
    assert sorted({(finding.path, finding.kind) for finding in findings}) == [
        ("docs/proposal_execution/automated_track/WHY_THRESHOLD_ONLY_FAILED.md", "figure_beside_a_product_name"),
        ("outputs/a1_diagnosis/figure.json", "figure_beside_a_product_name"),
        ("outputs/a1_diagnosis/nested.json", "figure_beside_a_product_name"),
        ("outputs/planning_v1/README.md", "figure_beside_a_product_name"),
        ("tests/test_a1_diagnosis_outputs.py", "figure_beside_a_product_name"),
    ]
    page = [finding for finding in findings if finding.path.endswith("WHY_THRESHOLD_ONLY_FAILED.md")]
    assert "line 2" in page[0].detail and page[0].products == ("ait",)
    readme = [finding for finding in findings if finding.path.endswith("README.md")]
    assert len(readme) == 1 and "line 5" in readme[0].detail, "only the section of plan task A1 is read"
    nested = [finding for finding in findings if finding.path.endswith("nested.json")]
    assert "$.against_the_AIT_extent" in nested[0].detail, "the name and the number are on different lines of the file"


def test_the_files_of_the_diagnosis_hold_no_figure_beside_either_name() -> None:
    files = guard.repository_files(ROOT)
    covered = [name for name in files if any(Path(name).match(pattern) for pattern in guard.A1_FILE_PATTERNS)]
    assert "docs/proposal_execution/automated_track/WHY_THRESHOLD_ONLY_FAILED.md" in covered
    assert "tests/test_a1_diagnosis_outputs.py" in covered and "outputs/planning_v1/README.md" in guard.A1_SECTIONS
    assert len([name for name in covered if name.startswith("scripts/diagnostics/")]) >= 7
    assert len([name for name in covered if name.startswith("outputs/planning_v1/a1_diagnosis_")]) >= 7
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
    # The command says that no hook is installed.
    assert "installs no hook" in " ".join((module.__doc__ or "").split())


def test_a_missing_or_malformed_baseline_is_refused(tmp_path: Path) -> None:
    with pytest.raises(guard.GuardError, match="missing"):
        guard.load_baseline(tmp_path)
    _write(tmp_path, guard.BASELINE_PATH.as_posix(), json.dumps({"schema": "other", "files": {}}))
    with pytest.raises(guard.GuardError, match="schema"):
        guard.load_baseline(tmp_path)
    _write(tmp_path, guard.BASELINE_PATH.as_posix(), json.dumps({"schema": guard.BASELINE_SCHEMA, "files": {"a.py": {"products": ["ait"]}}}))
    with pytest.raises(guard.GuardError, match="a.py"):
        guard.load_baseline(tmp_path)
    entry = {"products": ["ait"], "naming_lines_sha256": "0" * 64, "definitions_sha256": "short"}
    _write(tmp_path, guard.BASELINE_PATH.as_posix(), json.dumps({"schema": guard.BASELINE_SCHEMA, "files": {"a.py": entry}}))
    with pytest.raises(guard.GuardError, match="definitions"):
        guard.load_baseline(tmp_path)


def test_an_f_string_is_one_string_literal_on_every_python_version() -> None:
    # From Python 3.12 the tokenizer splits an f-string into parts. Read that way, its short parts became
    # naming lines on 3.12 and not on 3.11, so the baseline held on one version and failed on the other.
    source = 'x = (\n    f"AIT reference-candidate {field} changed; "\n    f"see {other.name}"\n)\n'
    tokens = list(guard._python_tokens(source))
    assert [value for _, kind, value in tokens if kind == "string"] == [
        'f"AIT reference-candidate {field} changed; " f"see {other.name}"'
    ]
    assert [value for _, kind, value in tokens if kind == "identifier"] == ["x"]
    assert sorted(value for _, _, value in guard._fstring_identifiers(source)) == ["field", "name", "other"]
