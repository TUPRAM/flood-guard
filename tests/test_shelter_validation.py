"""Tests for the shelter-candidate verification sheet's import rules.

``floodguard.shelter_validation`` judges a returned sheet; ``scripts/import_shelter_validation.py`` reads the
file, keeps it out of the repository and writes the derived document; the bake turns that document, or its
absence, into what the replay says. Every returned sheet here is made up for the test: no check has been
conducted, and no test states a result for a real site.
"""

from __future__ import annotations

import csv
from datetime import date
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys

import pytest

from floodguard import replay_exports as exports
from floodguard import shelter_validation as rules
from floodguard.shelter_validation import ShelterValidationError

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
IMPORTED_ON = date(2026, 10, 20)
CANDIDATES = [
    {"id": "C001", "kind": "school", "name": "โรงเรียนบ้านตัวอย่าง", "lon": 99.88, "lat": 20.43, "capacity_est": 120, "eligible": True},
    {"id": "C002", "kind": "worship", "name": "", "lon": 99.89, "lat": 20.44, "capacity_est": None, "eligible": True},
    {"id": "C003", "kind": "government", "name": "Office", "lon": 99.87, "lat": 20.42, "capacity_est": 40, "eligible": False},
    {"id": "C004", "kind": "community", "name": "Hall", "lon": 99.9, "lat": 20.45, "capacity_est": 60, "eligible": True},
]
FINGERPRINT = exports.candidate_set_sha256(CANDIDATES)
BASIS = {"estimate": "OSM footprint x 0.5 / 3.5 m2 (Sphere), unverified", "unknown": "unknown"}


def blank_sheet() -> bytes:
    """A blank sheet for the three eligible candidates, written like the bake writes it."""
    rows = []
    for site in exports.sheet_candidates(CANDIDATES):
        row = {"candidate_id": site["id"], "kind": site["kind"], "name": site["name"], "lat": site["lat"], "lon": site["lon"],
               "estimated_capacity": site["capacity_est"], "capacity_basis": BASIS["unknown" if site["capacity_est"] is None else "estimate"]}
        row.update({column.key: None for column in exports.SHEET_CHECKER})
        rows.append(row)
    fields = [("title", "Shelter-candidate verification sheet"), ("generated_at", "2026-10-02T15:00:00+07:00"),
              ("candidate_set_sha256", FINGERPRINT), ("verification_status", "not_conducted")]
    return exports.csv_bytes("shelter_candidate_verification_sheet.csv", fields, exports.SHEET_COLUMNS, rows)[0]


SHEET_ROWS = exports.read_export_csv(blank_sheet())[2]


def returned(answers: dict[str, dict[str, str]], *, extra_columns: dict[str, str] | None = None, keep_provenance: bool = True,
             header: list[str] | None = None, pad: int = 0) -> str:
    """A returned sheet as text: the blank sheet with ``answers`` filled in per candidate id.

    ``extra_columns`` adds columns (heading to one value for every row), ``pad`` appends empty cells to every line as
    a spreadsheet does, and ``keep_provenance=False`` drops the provenance lines.
    """
    lines = list(csv.reader(io.StringIO(blank_sheet().decode("utf-8-sig"), newline="")))
    start = next(index for index, cells in enumerate(lines) if not cells[0].startswith("#"))
    provenance, head, body = lines[:start], lines[start], lines[start + 1:]
    keys = [cell.split(" (", 1)[0] for cell in head]
    for cells in body:
        for key, value in answers.get(cells[0], {}).items():
            cells[keys.index(key)] = value
    if header is not None:
        head = header
    for heading, value in (extra_columns or {}).items():
        head = [*head, heading]
        body = [[*cells, value] for cells in body]
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    for cells in [*(provenance if keep_provenance else []), head, *body]:
        writer.writerow([*cells, *[""] * pad])
    return out.getvalue()


GOOD = {"C001": {"usable_as_shelter": "yes", "verified_capacity": "150", "access_notes": "Paved road to the gate", "checked_by_role": "village_leader",
                 "checked_on": "2026-10-09"},
        "C004": {"usable_as_shelter": "no", "checked_by_role": "local_government_officer", "checked_on": "2026-10-10"}}


def check(text: str, **options) -> list[dict]:
    return rules.validate_returned_sheet(text, SHEET_ROWS, FINGERPRINT, IMPORTED_ON, **options)


def refused(text: str, **options) -> list[str]:
    with pytest.raises(ShelterValidationError) as error:
        check(text, **options)
    return error.value.problems


# --- A good return ---------------------------------------------------------------------------------------------


def test_a_filled_sheet_gives_only_the_whitelisted_columns_of_the_checked_candidates() -> None:
    rows = check(returned(GOOD))
    assert rows == [
        {"candidate_id": "C001", "usable_as_shelter": True, "verified_capacity": 150, "checked_by_role": "village_leader",
         "checked_on": "2026-10-09", "access_notes_given": True},
        {"candidate_id": "C004", "usable_as_shelter": False, "verified_capacity": None, "checked_by_role": "local_government_officer",
         "checked_on": "2026-10-10", "access_notes_given": False},
    ]
    assert all(tuple(row) == rules.DERIVED_KEYS for row in rows)
    # C002 was left empty: it is not a check, and nothing is said about it.
    assert "C002" not in [row["candidate_id"] for row in rows]
    # The free-text note is kept only on request.
    with_notes = check(returned(GOOD), include_access_notes=True)
    assert with_notes[0]["access_notes"] == "Paved road to the gate" and with_notes[1]["access_notes"] == ""


def test_a_spreadsheet_round_trip_is_read_padded_cells_thai_answers_and_local_dates() -> None:
    answers = {"C001": {"usable_as_shelter": "ใช่", "verified_capacity": "1,200", "checked_by_role": "เจ้าหน้าที่ ปภ.", "checked_on": "9/10/2569"},
               "C002": {"usable_as_shelter": "ไม่ได้", "checked_by_role": "DDPM officer", "checked_on": "10-10-2026"}}
    rows = check(returned(answers, pad=4, keep_provenance=False))
    assert [(row["candidate_id"], row["usable_as_shelter"], row["verified_capacity"], row["checked_by_role"], row["checked_on"]) for row in rows] == [
        ("C001", True, 1200, "ddpm_officer", "2026-10-09"), ("C002", False, None, "ddpm_officer", "2026-10-10")]
    # Saved by a Thai Windows spreadsheet: Windows-874 bytes decode to the same sheet.
    data = returned(answers).encode("cp874")
    text, encoding = rules.decode_returned(data)
    assert encoding == "cp874" and check(text) == rows
    assert rules.decode_returned(blank_sheet())[1] == "utf-8-sig"
    with pytest.raises(ShelterValidationError, match="neither UTF-8 nor Windows-874"):
        rules.decode_returned(b"\x81\x82\xdb\xdc")


def test_value_parsers() -> None:
    assert [rules.parse_usable(value) for value in ("yes", " YES ", "y", "ได้", "no", "ไม่ใช่", "maybe", "")] == [
        True, True, True, True, False, False, None, None]
    assert rules.parse_role("village_leader") == rules.parse_role("Village head or kamnan") == rules.parse_role("ผู้ใหญ่บ้านหรือกำนัน") == "village_leader"
    assert rules.parse_role("นายสมชาย ใจดี") is None and rules.parse_role("Somchai") is None and rules.parse_role("") is None
    assert sorted(exports.CHECKER_ROLES) == ["ddpm_officer", "local_government_officer", "other_local_contact", "project_team", "site_staff", "village_leader"]
    parse = rules.parse_check_date
    assert parse("2026-10-09") == parse("9/10/2026") == parse("09.10.2026") == parse("9/10/2569") == parse("2569-10-09") == date(2026, 10, 9)
    assert parse("2026-13-01") is None and parse("31/02/2026") is None and parse("next week") is None and parse("") is None
    assert rules.column_key("usable_as_shelter (ใช้เป็นที่พักพิงได้หรือไม่)") == "usable_as_shelter"
    assert rules.check_label("ddpm_officer", "2026-10-09") == "Checked by a DDPM officer on 2026-10-09; not an official shelter register"
    assert rules.check_label("site_staff", "2026-10-09") == "Checked by staff of the site on 2026-10-09; not an official shelter register"
    with pytest.raises(ShelterValidationError):
        rules.check_label("Somchai", "2026-10-09")


# --- Personal data ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("heading", "kind"), [
    ("checker_name", "a person's name"), ("Name of checker", "a person's name"), ("contact name", "a person's name"), ("full_name", "a person's name"),
    ("checked_by", "a person's name"), ("ชื่อผู้ตรวจสอบ", "a person's name"), ("ชื่อ-นามสกุล", "a person's name"), ("นามสกุล", "a person's name"),
    ("phone", "a phone number"), ("Tel", "a phone number"), ("mobile number", "a phone number"), ("เบอร์โทรศัพท์", "a phone number"),
    ("Line ID", "a phone number"), ("เบอร์ติดต่อ", "a phone number"),
    ("ID number", "an ID number"), ("national_id", "an ID number"), ("เลขบัตรประชาชน", "an ID number"), ("เลขประจำตัวประชาชน", "an ID number"),
    ("email", "an e-mail address"), ("อีเมล", "an e-mail address"), ("home address", "a home address"), ("ที่อยู่", "a home address"),
])
def test_a_personal_data_column_is_refused_whatever_it_holds(heading: str, kind: str) -> None:
    assert rules.personal_data_kind(heading) == kind
    for value in ("", "anything"):
        problems = refused(returned(GOOD, extra_columns={heading: value}))
        assert problems == [f"column 13 asks for {kind}: personal data is not accepted; remove the column and send the file again"]


def test_the_sheets_own_columns_are_not_mistaken_for_personal_data() -> None:
    for column in exports.SHEET_COLUMNS:
        assert rules.column_key(column.label) in rules.SHEET_KEYS
    assert rules.personal_data_kind("remarks") is None and rules.personal_data_kind("roof type") is None
    assert check(returned(GOOD))  # name (the site's name) and checked_by_role are on the whitelist.


def test_an_unknown_column_is_refused_and_an_empty_trailing_one_is_ignored() -> None:
    assert refused(returned(GOOD, extra_columns={"remarks": "none"})) == ["column 13 is not on the sheet's whitelist; remove it"]
    assert check(returned(GOOD, extra_columns={"": ""}))  # A spreadsheet's empty trailing column.
    assert refused(returned(GOOD, extra_columns={"": "a stray value"})) == ["column 13 has no heading but holds values; remove it"]
    head = [column.label for column in exports.SHEET_COLUMNS]
    assert refused(returned(GOOD, header=[*head[:-1], "name (ชื่อ)"])) == ["column name appears twice", "column checked_on is missing"]
    assert "column usable_as_shelter is missing" in refused(returned(GOOD, header=[cell for cell in head if not cell.startswith("usable")] + [""]))


@pytest.mark.parametrize(("note", "kind"), [
    ("call 081-234-5678 first", "a phone number"), ("0812345678", "a phone number"), ("+66 81 234 5678", "a phone number"),
    ("053 731 234", "a phone number"), ("key holder 1-2345-67890-12-3", "an ID number"), ("1234567890123", "an ID number"),
    ("write to somchai@example.org", "an e-mail address"),
])
def test_a_cell_that_reads_as_personal_data_is_refused_without_repeating_it(note: str, kind: str) -> None:
    assert rules.personal_data_in_value(note) == kind
    problems = refused(returned({"C001": {**GOOD["C001"], "access_notes": note}}))
    assert problems == [f"data row 1, column 10: the cell reads as {kind}; personal data is not accepted"]
    assert note not in "\n".join(problems) and "5678" not in "\n".join(problems)  # The message never repeats the cell.
    for column in ("checked_by_role", "name"):
        assert any("personal data is not accepted" in problem for problem in refused(returned({"C001": {**GOOD["C001"], column: note}})))


def test_ordinary_answers_are_not_read_as_personal_data() -> None:
    for value in ("2026-10-09", "9/10/2569", "150", "20.329773", "99.863965", "Road 6 m wide, 200 m from Highway 1", "ห่างจากถนนใหญ่ 200 เมตร ชั้น 2",
                  "OSM footprint x 0.5 / 3.5 m2 (Sphere), unverified", "open 08:00-17:00"):
        assert rules.personal_data_in_value(value) is None, value


def test_notes_that_name_a_person_are_refused_when_the_notes_are_kept() -> None:
    for note in ("ติดต่อ นายสมชาย ก่อนเข้า", "Ask Mr. Somchai for the key", "น.ส.มาลี ถือกุญแจ"):
        answers = {"C001": {**GOOD["C001"], "access_notes": note}}
        assert refused(returned(answers), include_access_notes=True) == [
            "data row 1 (C001): access_notes seems to name a person; remove the name or import without the notes"]
        rows = check(returned(answers))  # Without the notes nothing of the text is kept, only that a note was given.
        assert rows[0]["access_notes_given"] is True and "access_notes" not in rows[0]
    assert len(refused(returned({"C001": {**GOOD["C001"], "access_notes": "x" * 301}}))) == 1


# --- Unknown candidates and malformed values ----------------------------------------------------------------------------


def test_unknown_or_repeated_candidates_and_another_candidate_list_are_refused() -> None:
    text = returned(GOOD)
    assert refused(text.replace("\nC004,", "\nC099,")) == ["data row 3: the candidate id is not on the sheet"]
    assert refused(text.replace("\nC004,", "\nC003,")) == ["data row 3: the candidate id is not on the sheet"]  # C003 is not eligible: not on the sheet.
    assert refused(text.replace("\nC004,", "\nC001,")) == ["data row 3: candidate C001 appears twice"]
    # The ids were renumbered since the sheet went out: the row no longer describes the same site.
    assert refused(returned({"C001": {**GOOD["C001"], "kind": "worship"}})) == [
        "data row 1 (C001): the kind differs from the sheet; the file may answer another candidate list"]
    assert refused(returned({"C001": {**GOOD["C001"], "lat": "20.5"}})) == [
        "data row 1 (C001): lat differs from the sheet; the file may answer another candidate list"]
    assert check(returned({"C001": {**GOOD["C001"], "name": "A corrected name", "lat": "20.430000"}}))  # A changed name is ignored, never copied.
    assert refused(text.replace(FINGERPRINT, "0" * 64)) == [
        "the file answers another candidate list (candidate_set_sha256 differs); send out the current sheet again"]
    with pytest.raises(ShelterValidationError, match="another candidate list"):
        rules.validate_returned_sheet(text, SHEET_ROWS, "f" * 64, IMPORTED_ON)


@pytest.mark.parametrize(("change", "message"), [
    ({"usable_as_shelter": "maybe"}, "usable_as_shelter must be yes or no"),
    ({"usable_as_shelter": ""}, "usable_as_shelter must be yes or no"),
    ({"verified_capacity": "12.5"}, "verified_capacity must be a whole number of people"),
    ({"verified_capacity": "-3"}, "verified_capacity must be a whole number of people"),
    ({"verified_capacity": "about 100"}, "verified_capacity must be a whole number of people"),
    ({"verified_capacity": "20001"}, "verified_capacity is above 20000"),
    ({"checked_by_role": "Somchai"}, "checked_by_role must be one of the role codes on the sheet (a role, never a name)"),
    ({"checked_by_role": ""}, "checked_by_role must be one of the role codes on the sheet (a role, never a name)"),
    ({"checked_on": "next week"}, "checked_on must be a date written YYYY-MM-DD"),
    ({"checked_on": ""}, "checked_on must be a date written YYYY-MM-DD"),
    ({"checked_on": "2026-10-21"}, "checked_on must lie between 2024-09-20 and the import date 2026-10-20"),
    ({"checked_on": "2024-09-12"}, "checked_on must lie between 2024-09-20 and the import date 2026-10-20"),
])
def test_a_malformed_answer_is_refused(change: dict[str, str], message: str) -> None:
    assert refused(returned({"C001": {**GOOD["C001"], **change}})) == [f"data row 1 (C001): {message}"]


def test_every_problem_is_reported_at_once_and_an_empty_sheet_is_not_a_check() -> None:
    answers = {"C001": {"usable_as_shelter": "perhaps", "checked_by_role": "ผู้ใหญ่สมชาย", "checked_on": "soon"}, "C004": {"verified_capacity": "many"}}
    assert refused(returned(answers)) == [
        "data row 1 (C001): usable_as_shelter must be yes or no",
        "data row 1 (C001): checked_by_role must be one of the role codes on the sheet (a role, never a name)",
        "data row 1 (C001): checked_on must be a date written YYYY-MM-DD",
        "data row 3 (C004): usable_as_shelter must be yes or no",
        "data row 3 (C004): verified_capacity must be a whole number of people",
        "data row 3 (C004): checked_by_role must be one of the role codes on the sheet (a role, never a name)",
        "data row 3 (C004): checked_on must be a date written YYYY-MM-DD",
    ]
    assert refused(blank_sheet().decode("utf-8-sig")) == ["no candidate was checked: every checker column is empty"]
    assert refused("# title,only provenance\n") == ["the file has no column header"]


# --- The derived document ---------------------------------------------------------------------------------------------


def document(rows: list[dict] | None = None) -> dict:
    return rules.check_document(rows if rows is not None else check(returned(GOOD)), returned_sha256="a" * 64, returned_bytes=1234,
                                returned_encoding="utf-8-sig", candidate_set_sha256=FINGERPRINT, candidates_listed=3, imported_on=IMPORTED_ON,
                                study_id="mae-sai-2024-flood-timeline", revision="r4", generated_by="scripts/import_shelter_validation.py")


def test_derived_document_carries_provenance_the_file_hash_and_nothing_else() -> None:
    doc = document()
    assert doc["schema"] == "floodguard.shelter_candidate_check.v1" and doc["status"] == "conducted"
    assert doc["label_template"] == "Checked by <role> on <date>; not an official shelter register"
    assert doc["source_timestamp"] == "checks dated 2026-10-09/2026-10-10" and doc["imported_on"] == "2026-10-20"
    assert doc["confidence"] == "low" and doc["confidence_reason"] and len(doc["assumptions"]) >= 3
    assert doc["official_warning"] is False and doc["operational_status"] == "non_operational"
    assert doc["returned_file"] == {"sha256": "a" * 64, "bytes": 1234, "encoding": "utf-8-sig", "kept": "outside the repository"}
    assert doc["sheet"] == {"candidate_set_sha256": FINGERPRINT, "candidates_listed": 3}
    assert doc["counts"] == {"checked": 2, "usable_yes": 1, "usable_no": 1, "with_verified_capacity": 1}
    assert all(set(row) == set(rules.DERIVED_KEYS) for row in doc["rows"])
    text = json.dumps(doc, ensure_ascii=False)
    assert "Paved road" not in text and "โรงเรียน" not in text  # Neither the notes nor the prefilled columns are copied.
    ids = ["C001", "C002", "C004"]
    assert rules.document_problems(doc, ids, FINGERPRINT) == []


def test_a_document_for_another_candidate_list_or_with_extra_columns_is_not_published() -> None:
    doc, ids = document(), ["C001", "C002", "C004"]
    problems = rules.document_problems
    assert problems(doc, ids, "f" * 64) == ["the check answers another candidate list (candidate_set_sha256 differs); the sheet must be sent out again"]
    assert problems(doc, ["C001"], FINGERPRINT) == ["C004: not a candidate of this revision"]
    assert problems({**doc, "rows": [{**doc["rows"][0], "checker_name": "x"}]}, ids, FINGERPRINT) == ["C001: columns outside the whitelist: ['checker_name']"]
    assert problems({**doc, "rows": [{**doc["rows"][0], "access_notes": "call 0812345678"}]}, ids, FINGERPRINT) == ["C001: a value reads as personal data"]
    assert problems({**doc, "rows": [{**doc["rows"][0], "checked_by_role": "Somchai"}]}, ids, FINGERPRINT) == ["C001: checked_by_role must be a role code"]
    assert problems({**doc, "rows": [doc["rows"][0], doc["rows"][0]]}, ids, FINGERPRINT) == ["C001: appears twice"]
    assert problems({**doc, "rows": [{**doc["rows"][0], "usable_as_shelter": "yes", "verified_capacity": 1.5, "checked_on": "soon"}]}, ids, FINGERPRINT) == [
        "C001: usable_as_shelter must be true or false", "C001: verified_capacity must be a whole number of people", "C001: checked_on must be a date"]
    assert "rows must list at least one checked candidate" in problems({**doc, "rows": []}, ids, FINGERPRINT)
    assert "status must be conducted: a check that was not conducted has no document" in problems({**doc, "status": "not_conducted"}, ids, FINGERPRINT)
    assert "returned_file.sha256 is missing" in problems({**doc, "returned_file": {}}, ids, FINGERPRINT)
    assert "source_timestamp is missing" in problems({key: value for key, value in doc.items() if key != "source_timestamp"}, ids, FINGERPRINT)
    assert problems([], ids, FINGERPRINT) == ["the check document is not an object"]


# --- The import script ---------------------------------------------------------------------------------------------


def load(name: str):
    sys.path.insert(0, str(SCRIPTS))
    try:
        spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(SCRIPTS))
    return module


@pytest.fixture()
def workspace(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A blank sheet, a returned copy outside the repository and a place for the derived document."""
    sheet = tmp_path / "blank" / "shelter_candidate_verification_sheet.csv"
    sheet.parent.mkdir()
    sheet.write_bytes(blank_sheet())
    back = tmp_path / "external" / "returned.csv"
    back.parent.mkdir()
    back.write_bytes(exports.BOM + returned(GOOD).encode("utf-8"))
    return sheet, back, tmp_path / "out" / "check.json"


def test_script_hashes_the_returned_file_and_writes_only_the_derived_document(workspace, capsys: pytest.CaptureFixture[str]) -> None:
    script = load("import_shelter_validation")
    sheet, back, out = workspace
    before = back.read_bytes()
    assert script.main([str(back), "--sheet", str(sheet), "--out", str(out), "--imported-on", "2026-10-20"]) == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["returned_file"]["sha256"] == hashlib.sha256(before).hexdigest() and doc["returned_file"]["bytes"] == len(before)
    assert doc["generated_by"] == "scripts/import_shelter_validation.py" and doc["counts"]["checked"] == 2
    assert [row["candidate_id"] for row in doc["rows"]] == ["C001", "C004"] and "access_notes" not in doc["rows"][0]
    assert rules.document_problems(doc, ["C001", "C002", "C004"], FINGERPRINT) == []
    assert b"\r" not in out.read_bytes() and str(back.parent) not in out.read_text(encoding="utf-8")  # LF, and no machine path.
    assert back.read_bytes() == before  # The returned file is read, never changed.
    printed = capsys.readouterr().out
    assert "checked: 2 of 3 candidates (1 usable, 1 not usable, 1 with a capacity)" in printed and "dates understood: checks dated 2026-10-09/2026-10-10" in printed


def test_script_writes_nothing_when_the_file_is_refused_or_only_checked(workspace, capsys: pytest.CaptureFixture[str]) -> None:
    script = load("import_shelter_validation")
    sheet, back, out = workspace
    assert script.main([str(back), "--sheet", str(sheet), "--out", str(out), "--imported-on", "2026-10-20", "--check"]) == 0
    assert not out.exists() and "check only: nothing was written." in capsys.readouterr().out
    back.write_text(returned(GOOD, extra_columns={"เบอร์โทร": "0812345678"}), encoding="utf-8")
    assert script.main([str(back), "--sheet", str(sheet), "--out", str(out), "--imported-on", "2026-10-20"]) == 1
    errors = capsys.readouterr().err
    assert not out.exists() and "column 13 asks for a phone number" in errors and "Nothing was written." in errors
    assert "0812345678" not in errors


def test_script_refuses_a_returned_file_inside_the_repository(workspace, tmp_path: Path) -> None:
    script = load("import_shelter_validation")
    sheet, back, _ = workspace
    options = {"study_id": "s", "revision": "r4"}
    with pytest.raises(ShelterValidationError, match="inside the repository: keep it outside Git"):
        script.import_returned(back, sheet, IMPORTED_ON, repository=tmp_path, **options)
    assert script.import_returned(back, sheet, IMPORTED_ON, repository=tmp_path / "blank", **options)["counts"]["checked"] == 2
    assert script.inside(ROOT / "outputs" / "anything.csv", ROOT) and not script.inside(tmp_path / "x.csv", ROOT)
    # No returned sheet is committed: the derived document is the only trace a return leaves in the repository.
    assert script.OUTPUT_REL.as_posix() == "outputs/mae_sai_shelter_validation.json"
    assert script.default_sheet().name == "shelter_candidate_verification_sheet.csv" and script.default_sheet().parent.name == "exports"


def test_script_reads_the_committed_blank_sheet() -> None:
    script = load("import_shelter_validation")
    sheet = script.default_sheet()
    fields, keys, rows = exports.read_export_csv(sheet.read_bytes())
    assert keys == list(rules.SHEET_KEYS) and len(fields["candidate_set_sha256"]) == 64 and len(rows) > 50
    assert all(row[key] == "" for row in rows for key in rules.CHECKER_KEYS)  # Blank: no check has been conducted.


# --- What the bake says ---------------------------------------------------------------------------------------------


def test_bake_says_not_conducted_without_a_document_and_labels_every_row_with_one() -> None:
    for dependency in ("PIL", "pyproj", "rasterio", "scipy", "shapely"):
        pytest.importorskip(dependency)
    bake = load("build_mae_sai_flood_timeline")
    nothing = bake.shelter_check(None, CANDIDATES, FINGERPRINT)
    assert nothing == {"status": "not_conducted", "label_template": "Checked by <role> on <date>; not an official shelter register",
                       "sheet": "shelter_candidate_verification_sheet", "candidate_set_sha256": FINGERPRINT, "candidates_listed": 3,
                       "statement": bake.VERIFICATION_NOT_CONDUCTED, "checked": []}
    assert "was not conducted" in nothing["statement"]
    conducted = bake.shelter_check(document(check(returned(GOOD), include_access_notes=True)), CANDIDATES, FINGERPRINT)
    assert conducted["status"] == "conducted" and conducted["counts"]["checked"] == 2 and conducted["returned_file_sha256"] == "a" * 64
    assert [row["label"] for row in conducted["checked"]] == [
        "Checked by a village head or kamnan on 2026-10-09; not an official shelter register",
        "Checked by a tambon or municipality officer on 2026-10-10; not an official shelter register"]
    assert conducted["checked"][0]["access_notes"] == "Paved road to the gate" and "access_notes" not in conducted["checked"][1]
    assert "not an official shelter register" in conducted["statement"] and conducted["source_timestamp"] == "checks dated 2026-10-09/2026-10-10"
    with pytest.raises(ValueError, match="cannot be published"):
        bake.shelter_check(document(), CANDIDATES, "f" * 64)
    assert bake.SHELTER_VALIDATION.as_posix() == "outputs/mae_sai_shelter_validation.json"
