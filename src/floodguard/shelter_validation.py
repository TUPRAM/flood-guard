"""Checks for a returned shelter-candidate verification sheet.

The Mae Sai replay ships a blank sheet (``exports/shelter_candidate_verification_sheet.csv``):
one row per eligible shelter candidate, with five empty columns for a local
checker. When someone returns it, ``scripts/import_shelter_validation.py`` runs
the rules here before anything derived from it is kept:

* the file may hold only the sheet's whitelisted columns. A column for a
  person's name, a phone number, an ID number, an e-mail or a home address is
  refused, and so is any other unknown column;
* no cell may hold something that reads as a phone number, an ID number or an
  e-mail address;
* every candidate id must be on the sheet, once, and still describe the same
  site (kind and position);
* every checked row needs ``usable_as_shelter`` (yes or no), a role code (never
  a name) and the date of the check; a capacity is a whole number of people.

Only the whitelisted checker columns are returned, as a document that carries
the returned file's hash, a source timestamp, a confidence and its assumptions.
The free-text notes are left out unless the caller asks for them. The returned
file itself stays outside the repository.

A check is labelled "Checked by <role> on <date>; not an official shelter
register". Nothing here invents a result: without a returned file there is no
document, and the replay says the check was not conducted.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import csv
from datetime import date
import hashlib
import io
import re
from typing import Any

from floodguard.replay_exports import CHECKER_ROLES, SHEET_CHECKER, SHEET_COLUMNS, SHEET_PREFILLED, VERIFICATION_LABEL

CHECK_SCHEMA = "floodguard.shelter_candidate_check.v1"
STATUS_CONDUCTED = "conducted"
STATUS_NOT_CONDUCTED = "not_conducted"

SHEET_KEYS: tuple[str, ...] = tuple(column.key for column in SHEET_COLUMNS)
CHECKER_KEYS: tuple[str, ...] = tuple(column.key for column in SHEET_CHECKER)
PREFILLED_KEYS: tuple[str, ...] = tuple(column.key for column in SHEET_PREFILLED)
DERIVED_KEYS: tuple[str, ...] = ("candidate_id", "usable_as_shelter", "verified_capacity", "checked_by_role", "checked_on", "access_notes_given")
"""Columns the derived document may hold for each checked candidate (``access_notes`` only on request)."""

MAX_VERIFIED_CAPACITY = 20000
MAX_NOTE_LENGTH = 300
EARLIEST_CHECK = date(2024, 9, 20)
"""A check cannot be dated before the end of the 2024 event the sheet is about."""

ENCODINGS: tuple[str, ...] = ("utf-8-sig", "cp874")
"""A spreadsheet saves CSV as UTF-8, or on a Thai Windows machine as Windows-874."""

_PERSONAL_COLUMNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("a person's name", re.compile(
        r"(?:checker|inspector|contact|person|officer|staff|respondent|informant|owner|head|leader|reviewer|verifier|first|last|sur|full|given|family)"
        r"[ _-]*names?|names? of|(?<![a-z])checked[ _-]*by(?![ _-]*role)|ชื่อผู้|ชื่อ ?- ?สกุล|ชื่อ ?- ?นามสกุล|นามสกุล|ชื่อบุคคล|ชื่อเจ้าหน้าที่|ชื่อและนามสกุล|ผู้ให้ข้อมูล")),
    ("a phone number", re.compile(r"phone|(?<![a-z])tel(?![a-z])|telephone|mobile|line[ _-]?id|whatsapp|โทร|เบอร์|มือถือ|ไลน์")),
    ("an ID number", re.compile(r"(?<![a-z])id[ _-]*(?:no|number|card)|national[ _-]*id|citizen|passport|บัตรประชาชน|เลขประจำตัว|เลขบัตร|หนังสือเดินทาง")),
    ("an e-mail address", re.compile(r"e-?mail|อีเมล")),
    ("a home address", re.compile(r"(?<![a-z])address|ที่อยู่")),
)
_EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
_ID_NUMBER = re.compile(r"(?<!\d)\d[ -]?\d{4}[ -]?\d{5}[ -]?\d{2}[ -]?\d(?!\d)")
_PHONE = re.compile(r"(?<!\d)(?:\+?66|0)[ -]?\d(?:[ -]?\d){7,8}(?!\d)|(?<!\d)\d(?:[ -]?\d){8,}(?!\d)")
_NAME_MARKER = re.compile(r"(?:นาย|นางสาว|น\.ส\.|ด\.ช\.|ด\.ญ\.)\s*[ก-๙]{2,}|(?<![A-Za-z])(?:Mr|Mrs|Ms|Miss|Khun)\.?\s+[A-Z][a-z]+")
_ISO_DATE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_DAY_FIRST_DATE = re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$")
_YES = frozenset({"yes", "y", "true", "1", "ใช่", "ได้", "ใช้ได้"})
_NO = frozenset({"no", "n", "false", "0", "ไม่", "ไม่ใช่", "ไม่ได้", "ใช้ไม่ได้"})
_ROLE_LABELS = {label.casefold(): code for code, labels in CHECKER_ROLES.items() for label in (code, labels["en"], labels["th"], labels["by"])}


class ShelterValidationError(ValueError):
    """Raised when a returned sheet, or a derived check document, breaks the rules. ``problems`` lists every one."""

    def __init__(self, problems: Sequence[str]):
        self.problems = list(problems)
        super().__init__("the returned sheet was refused:\n  " + "\n  ".join(self.problems))


def file_sha256(data: bytes) -> str:
    """SHA-256 of the returned file's bytes, as lowercase hexadecimal."""
    return hashlib.sha256(data).hexdigest()


def decode_returned(data: bytes) -> tuple[str, str]:
    """Decode a returned CSV and say which encoding it was in. Raises when it is neither UTF-8 nor Windows-874."""
    for encoding in ENCODINGS:
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise ShelterValidationError(["the file is neither UTF-8 nor Windows-874 text; save it as CSV UTF-8"])


def column_key(cell: str) -> str:
    """The key of a header cell: ``usable_as_shelter (ใช้เป็นที่พักพิงได้หรือไม่)`` gives ``usable_as_shelter``."""
    return cell.split(" (", 1)[0].strip().lstrip("﻿")


def personal_data_kind(header_cell: str) -> str | None:
    """What kind of personal data a column heading asks for, or ``None``. The heading is read in English and Thai."""
    text = header_cell.casefold()
    for kind, pattern in _PERSONAL_COLUMNS:
        if pattern.search(text):
            return kind
    return None


def personal_data_in_value(text: str) -> str | None:
    """What kind of personal data a cell seems to hold (an e-mail, an ID number or a phone number), or ``None``."""
    if _EMAIL.search(text):
        return "an e-mail address"
    if _ID_NUMBER.search(text):
        return "an ID number"
    if _PHONE.search(text):
        return "a phone number"
    return None


def parse_usable(text: str) -> bool | None:
    """``True`` for yes, ``False`` for no (English or Thai), ``None`` for anything else."""
    value = text.strip().casefold()
    return True if value in _YES else False if value in _NO else None


def parse_role(text: str) -> str | None:
    """The role code for a code or its English or Thai label, or ``None``. A name is never a role."""
    return _ROLE_LABELS.get(text.strip().casefold())


def parse_check_date(text: str) -> date | None:
    """A date written ``YYYY-MM-DD``, or day first (``D/M/YYYY``) as a Thai spreadsheet saves it.

    A Buddhist-era year (2400 or later) is read as the CE year 543 earlier.
    """
    value = text.strip()
    match = _ISO_DATE.match(value)
    if match:
        year, month, day = (int(part) for part in match.groups())
    else:
        match = _DAY_FIRST_DATE.match(value)
        if not match:
            return None
        day, month, year = (int(part) for part in match.groups())
    if year >= 2400:
        year -= 543
    try:
        return date(year, month, day)
    except ValueError:
        return None


def read_returned_table(text: str) -> tuple[dict[str, str], list[str], list[list[str]]]:
    """Split a returned CSV into its provenance fields, its header cells and its data rows.

    Provenance lines (first cell starting with ``#``) and blank lines are skipped wherever they are: a spreadsheet
    keeps them as rows and may pad them with empty cells.
    """
    reader = csv.reader(io.StringIO(text, newline=""))
    fields: dict[str, str] = {}
    header: list[str] | None = None
    rows: list[list[str]] = []
    for cells in reader:
        cells = [cell.strip() for cell in cells]
        if not any(cells):
            continue
        if cells[0].startswith("#"):
            fields[cells[0].lstrip("# ").strip()] = cells[1] if len(cells) > 1 else ""
            continue
        if header is None:
            header = cells
            continue
        rows.append(cells)
    if header is None:
        raise ShelterValidationError(["the file has no column header"])
    return fields, header, rows


def validate_returned_sheet(
    text: str,
    sheet_rows: Sequence[Mapping[str, str]],
    candidate_set_sha256: str,
    imported_on: date,
    *,
    include_access_notes: bool = False,
) -> list[dict[str, Any]]:
    """Check a returned sheet and return the whitelisted columns of every checked candidate.

    Args:
        text: The returned CSV, decoded.
        sheet_rows: The rows of the blank sheet this file answers (keyed by column key).
        candidate_set_sha256: The blank sheet's candidate fingerprint.
        imported_on: The date of the import; a check dated later is refused.
        include_access_notes: Keep the free-text notes. Off by default: free text can name a person.

    Returns:
        One mapping per checked candidate with the keys of :data:`DERIVED_KEYS` (plus ``access_notes`` on
        request), sorted by candidate id. A row whose checker columns are all empty is not a check.

    Raises:
        ShelterValidationError: With every problem found. No message repeats a cell's content.
    """
    problems: list[str] = []
    fields, header, rows = read_returned_table(text)
    stated = fields.get("candidate_set_sha256")
    if stated and stated != candidate_set_sha256:
        problems.append("the file answers another candidate list (candidate_set_sha256 differs); send out the current sheet again")
    keys = [column_key(cell) for cell in header]
    index: dict[str, int] = {}
    for position, (key, cell) in enumerate(zip(keys, header)):
        if not cell:
            if any(position < len(row) and row[position] for row in rows):
                problems.append(f"column {position + 1} has no heading but holds values; remove it")
            continue
        if key in SHEET_KEYS:
            if key in index:
                problems.append(f"column {key} appears twice")
            index[key] = position
            continue
        kind = personal_data_kind(cell)
        if kind:
            problems.append(f"column {position + 1} asks for {kind}: personal data is not accepted; remove the column and send the file again")
        else:
            problems.append(f"column {position + 1} is not on the sheet's whitelist; remove it")
    for key in ("candidate_id", *CHECKER_KEYS):
        if key not in index:
            problems.append(f"column {key} is missing")
    if problems:
        raise ShelterValidationError(problems)

    known = {row["candidate_id"]: row for row in sheet_rows}
    seen: set[str] = set()
    derived: list[dict[str, Any]] = []
    for number, cells in enumerate(rows, start=1):
        cell = lambda key: cells[index[key]] if key in index and index[key] < len(cells) else ""  # noqa: E731
        where = f"data row {number}"
        for position, value in enumerate(cells):
            kind = personal_data_in_value(value) if position != index.get("lat") and position != index.get("lon") else None
            if kind:
                problems.append(f"{where}, column {position + 1}: the cell reads as {kind}; personal data is not accepted")
        candidate_id = cell("candidate_id")
        if candidate_id not in known:
            problems.append(f"{where}: the candidate id is not on the sheet")
            continue
        if candidate_id in seen:
            problems.append(f"{where}: candidate {candidate_id} appears twice")
            continue
        seen.add(candidate_id)
        where = f"{where} ({candidate_id})"
        problems.extend(f"{where}: {note}" for note in _site_differences(cell, known[candidate_id], index))
        answers = {key: cell(key) for key in CHECKER_KEYS}
        if not any(answers.values()):
            continue
        row_problems: list[str] = []
        usable = parse_usable(answers["usable_as_shelter"])
        if usable is None:
            row_problems.append("usable_as_shelter must be yes or no")
        capacity: int | None = None
        if answers["verified_capacity"]:
            if not re.fullmatch(r"\d{1,6}", answers["verified_capacity"].replace(",", "")):
                row_problems.append("verified_capacity must be a whole number of people")
            else:
                capacity = int(answers["verified_capacity"].replace(",", ""))
                if capacity > MAX_VERIFIED_CAPACITY:
                    row_problems.append(f"verified_capacity is above {MAX_VERIFIED_CAPACITY}")
        role = parse_role(answers["checked_by_role"])
        if role is None:
            row_problems.append("checked_by_role must be one of the role codes on the sheet (a role, never a name)")
        checked_on = parse_check_date(answers["checked_on"])
        if checked_on is None:
            row_problems.append("checked_on must be a date written YYYY-MM-DD")
        elif not EARLIEST_CHECK <= checked_on <= imported_on:
            row_problems.append(f"checked_on must lie between {EARLIEST_CHECK.isoformat()} and the import date {imported_on.isoformat()}")
        notes = answers["access_notes"]
        if len(notes) > MAX_NOTE_LENGTH:
            row_problems.append(f"access_notes is longer than {MAX_NOTE_LENGTH} characters")
        if include_access_notes and _NAME_MARKER.search(notes):
            row_problems.append("access_notes seems to name a person; remove the name or import without the notes")
        if row_problems:
            problems.extend(f"{where}: {note}" for note in row_problems)
            continue
        entry: dict[str, Any] = {"candidate_id": candidate_id, "usable_as_shelter": usable, "verified_capacity": capacity,
                                 "checked_by_role": role, "checked_on": checked_on.isoformat(), "access_notes_given": bool(notes)}
        if include_access_notes:
            entry["access_notes"] = notes
        derived.append(entry)
    if problems:
        raise ShelterValidationError(problems)
    if not derived:
        raise ShelterValidationError(["no candidate was checked: every checker column is empty"])
    return sorted(derived, key=lambda entry: entry["candidate_id"])


def _site_differences(cell, sheet_row: Mapping[str, str], index: Mapping[str, int]) -> list[str]:
    """Why a returned row no longer describes the sheet's candidate (kind or position changed)."""
    notes = []
    if "kind" in index and cell("kind") and cell("kind") != sheet_row["kind"]:
        notes.append("the kind differs from the sheet; the file may answer another candidate list")
    for key in ("lat", "lon"):
        if key not in index or not cell(key):
            continue
        try:
            moved = abs(float(cell(key)) - float(sheet_row[key])) > 1e-5
        except ValueError:
            moved = True
        if moved:
            notes.append(f"{key} differs from the sheet; the file may answer another candidate list")
    return notes


def check_label(role: str, checked_on: str) -> str:
    """The label of one check: "Checked by <role> on <date>; not an official shelter register"."""
    if role not in CHECKER_ROLES:
        raise ShelterValidationError([f"unknown role code: {role}"])
    return VERIFICATION_LABEL.replace("<role>", CHECKER_ROLES[role]["by"]).replace("<date>", checked_on)


def check_document(
    rows: Sequence[Mapping[str, Any]],
    *,
    returned_sha256: str,
    returned_bytes: int,
    returned_encoding: str,
    candidate_set_sha256: str,
    candidates_listed: int,
    imported_on: date,
    study_id: str,
    revision: str,
    generated_by: str,
) -> dict[str, Any]:
    """The derived document kept in the repository: the checked columns, the returned file's hash and its provenance."""
    dates = sorted(row["checked_on"] for row in rows)
    return {
        "schema": CHECK_SCHEMA,
        "study_id": study_id, "revision": revision, "generated_by": generated_by,
        "status": STATUS_CONDUCTED,
        "label_template": VERIFICATION_LABEL,
        "evidence_tier": "Local check reported by role; not an official shelter register",
        "source_timestamp": f"checks dated {dates[0]}/{dates[-1]}",
        "imported_on": imported_on.isoformat(),
        "confidence": "low",
        "confidence_reason": "One local check per site, reported by role and not audited by the project team.",
        "assumptions": [
            "Each row is what one local checker reported for one candidate; it is not an official shelter register.",
            "The returned file is kept outside the repository; only its SHA-256, its size and the whitelisted columns below are kept.",
            "A candidate without a row was not checked; nothing is implied about it.",
            "Free-text access notes are left out unless the import was run with the notes included.",
        ],
        "official_warning": False, "operational_status": "non_operational",
        "returned_file": {"sha256": returned_sha256, "bytes": returned_bytes, "encoding": returned_encoding, "kept": "outside the repository"},
        "sheet": {"candidate_set_sha256": candidate_set_sha256, "candidates_listed": candidates_listed},
        "counts": {"checked": len(rows), "usable_yes": sum(1 for row in rows if row["usable_as_shelter"]),
                   "usable_no": sum(1 for row in rows if not row["usable_as_shelter"]),
                   "with_verified_capacity": sum(1 for row in rows if row["verified_capacity"] is not None)},
        "rows": [dict(row) for row in rows],
    }


def document_problems(document: Any, candidate_ids: Iterable[str], candidate_set_sha256: str) -> list[str]:
    """Why a derived check document may not be published with this revision (empty when it may).

    The document must answer this revision's candidate list, name only its candidates, hold only whitelisted
    columns and carry its provenance.
    """
    if not isinstance(document, Mapping):
        return ["the check document is not an object"]
    problems = []
    if document.get("schema") != CHECK_SCHEMA:
        problems.append(f"schema must be {CHECK_SCHEMA}")
    if document.get("status") != STATUS_CONDUCTED:
        problems.append("status must be conducted: a check that was not conducted has no document")
    for key in ("source_timestamp", "confidence", "assumptions", "imported_on", "label_template"):
        if not document.get(key):
            problems.append(f"{key} is missing")
    returned = document.get("returned_file")
    if not isinstance(returned, Mapping) or not re.fullmatch(r"[0-9a-f]{64}", str(returned.get("sha256", ""))):
        problems.append("returned_file.sha256 is missing")
    sheet = document.get("sheet")
    if not isinstance(sheet, Mapping) or sheet.get("candidate_set_sha256") != candidate_set_sha256:
        problems.append("the check answers another candidate list (candidate_set_sha256 differs); the sheet must be sent out again")
    rows = document.get("rows")
    if not isinstance(rows, list) or not rows:
        problems.append("rows must list at least one checked candidate")
        return problems
    allowed = set(DERIVED_KEYS) | {"access_notes"}
    known = set(candidate_ids)
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            problems.append("a row is not an object")
            continue
        candidate_id = str(row.get("candidate_id"))
        extra = sorted(set(row) - allowed)
        if extra:
            problems.append(f"{candidate_id}: columns outside the whitelist: {extra}")
        if candidate_id not in known:
            problems.append(f"{candidate_id}: not a candidate of this revision")
        if candidate_id in seen:
            problems.append(f"{candidate_id}: appears twice")
        seen.add(candidate_id)
        if not isinstance(row.get("usable_as_shelter"), bool):
            problems.append(f"{candidate_id}: usable_as_shelter must be true or false")
        capacity = row.get("verified_capacity")
        if capacity is not None and (not isinstance(capacity, int) or isinstance(capacity, bool) or not 0 <= capacity <= MAX_VERIFIED_CAPACITY):
            problems.append(f"{candidate_id}: verified_capacity must be a whole number of people")
        if row.get("checked_by_role") not in CHECKER_ROLES:
            problems.append(f"{candidate_id}: checked_by_role must be a role code")
        if parse_check_date(str(row.get("checked_on", ""))) is None:
            problems.append(f"{candidate_id}: checked_on must be a date")
        for value in row.values():
            if isinstance(value, str) and personal_data_in_value(value):
                problems.append(f"{candidate_id}: a value reads as personal data")
    return problems
