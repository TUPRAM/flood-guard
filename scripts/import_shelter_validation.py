#!/usr/bin/env python
"""Import a returned shelter-candidate verification sheet for the Mae Sai replay.

The replay ships a blank sheet, ``exports/shelter_candidate_verification_sheet.csv``: one row per eligible
shelter candidate, with five empty columns for a local checker. When someone returns it, run::

    python scripts/import_shelter_validation.py <returned.csv>

The script

* refuses a returned file that sits inside the repository: the raw file is someone's answer and stays
  outside Git (keep it under the external data root);
* refuses personal data: a column for a person's name, a phone number, an ID number, an e-mail or an
  address, any other column that is not on the sheet, and any cell that reads as a phone number, an ID
  number, an e-mail address or a messaging id (digits are counted with their separators ignored);
* refuses an unknown candidate id, a candidate listed twice, a row that no longer describes the sheet's
  candidate, a file that has lost the sheet's ``# candidate_set_sha256`` line unless every checked row still
  carries the sheet's kind, latitude and longitude, and a malformed answer (``usable_as_shelter`` must be yes
  or no, ``verified_capacity`` a whole number, ``checked_by_role`` a role code and never a name,
  ``checked_on`` a date);
* hashes the returned file (SHA-256) and writes only the whitelisted checker columns, with that hash, to
  ``outputs/mae_sai_shelter_validation.json``. The free-text access notes are never written: no screen can
  recognise an untitled name, so only the fact that a note was given is kept. Whether notes may ever be
  published is an owner decision (decision log, follow-up 8b); until then there is no option to keep them.

The next bake reads that file and labels every row "Checked by <role> on <date>; not an official shelter
register". Without it the replay says the check was not conducted. The script invents nothing: a row whose
checker columns are empty is not a check. ``--check`` reads and judges the file and writes nothing.

A date is read as ``YYYY-MM-DD``. A spreadsheet on a Thai machine may save it day first (``9/10/2026``) or
with a Buddhist-era year; both are read, day first, and the script prints the range of dates it understood
so the importer can confirm it.
"""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard.replay_exports import EXPORT_FOLDER, read_export_csv  # noqa: E402
from floodguard.shelter_validation import (  # noqa: E402
    ShelterValidationError,
    check_document,
    decode_returned,
    file_sha256,
    validate_returned_sheet,
)

GENERATED_BY = "scripts/import_shelter_validation.py"
OUTPUT_REL = Path("outputs/mae_sai_shelter_validation.json")
SHEET_NAME = "shelter_candidate_verification_sheet.csv"
WEB = ROOT / "apps" / "web"


def served_manifest(root: Path = ROOT) -> Path:
    """The replay manifest the page serves, from the one constant in ``flood-timeline.ts``."""
    source = (root / "apps" / "web" / "src" / "lib" / "flood-timeline.ts").read_text(encoding="utf-8")
    href = re.search(r'TIMELINE_MANIFEST_URL = "([^"]+)"', source).group(1)
    return root / "apps" / "web" / "public" / href.lstrip("/")


def default_sheet(root: Path = ROOT) -> Path:
    """The blank sheet of the served revision."""
    return served_manifest(root).parent / EXPORT_FOLDER / SHEET_NAME


def inside(path: Path, folder: Path) -> bool:
    """True when ``path`` lies in ``folder`` (both resolved)."""
    try:
        path.resolve().relative_to(folder.resolve())
    except ValueError:
        return False
    return True


def import_returned(returned: Path, sheet: Path, imported_on: date, *, study_id: str, revision: str,
                    repository: Path | None = ROOT) -> dict:
    """Judge ``returned`` against the blank ``sheet`` and return the derived document (nothing is written).

    Raises :class:`floodguard.shelter_validation.ShelterValidationError` with every problem found. ``repository``
    is the folder the raw file must stay out of (``None`` skips that rule, for tests that work in one folder).
    """
    if repository is not None and inside(returned, repository):
        raise ShelterValidationError(["the returned file is inside the repository: keep it outside Git, for example under the external data root"])
    fields, _, sheet_rows = read_export_csv(sheet.read_bytes())
    candidate_set = fields.get("candidate_set_sha256", "")
    if not re.fullmatch(r"[0-9a-f]{64}", candidate_set):
        raise ShelterValidationError(["the blank sheet does not state its candidate_set_sha256"])
    data = returned.read_bytes()
    text, encoding = decode_returned(data)
    rows = validate_returned_sheet(text, sheet_rows, candidate_set, imported_on)
    return check_document(rows, returned_sha256=file_sha256(data), returned_bytes=len(data), returned_encoding=encoding,
                          candidate_set_sha256=candidate_set, candidates_listed=len(sheet_rows), imported_on=imported_on,
                          study_id=study_id, revision=revision, generated_by=GENERATED_BY)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("returned", help="The returned CSV (kept outside the repository).")
    parser.add_argument("--sheet", default=None, help="The blank sheet the file answers. Defaults to the served revision's sheet.")
    parser.add_argument("--out", default=str(ROOT / OUTPUT_REL), help="Where to write the derived document.")
    parser.add_argument("--imported-on", default=None, help="Date of the import, YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--check", action="store_true", help="Judge the file and print the result; write nothing.")
    args = parser.parse_args(argv)
    returned = Path(args.returned)
    if not returned.is_file():
        parser.error("the returned file does not exist")
    sheet = Path(args.sheet) if args.sheet else default_sheet()
    if not sheet.is_file():
        parser.error("the blank sheet was not found; bake the replay first or pass --sheet")
    try:
        imported_on = date.fromisoformat(args.imported_on) if args.imported_on else date.today()
    except ValueError:
        parser.error("--imported-on must be a date written YYYY-MM-DD")
    manifest = json.loads(served_manifest().read_text(encoding="utf-8"))
    try:
        document = import_returned(returned, sheet, imported_on, study_id=manifest["study_id"], revision=manifest["revision"])
    except ShelterValidationError as error:
        print(str(error), file=sys.stderr)
        print("Nothing was written.", file=sys.stderr)
        return 1
    counts = document["counts"]
    print(f"returned file: SHA-256 {document['returned_file']['sha256']}, {document['returned_file']['bytes']:,} bytes ({document['returned_file']['encoding']})")
    print(f"checked: {counts['checked']} of {document['sheet']['candidates_listed']} candidates "
          f"({counts['usable_yes']} usable, {counts['usable_no']} not usable, {counts['with_verified_capacity']} with a capacity)")
    print(f"dates understood: {document['source_timestamp']}")
    if args.check:
        print("check only: nothing was written.")
        return 0
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {out.name}; bake the replay again so the page shows the check.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
