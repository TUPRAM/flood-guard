"""Take in the acceptance records of the validation-check page.

The page at ``/studio/validation-check/`` hands a record over in one of two
ways: a GitHub issue with the label ``validation-check``, or a text file a team
member passes on. This script reads both, checks each record against the item
list, appends what is new to the log and rewrites the state the page shows.

Examples::

    python scripts/import_validation_records.py --github
    python scripts/import_validation_records.py --file <downloads>/validation-record-Rachmania.txt
    python scripts/import_validation_records.py --check          # rewrite nothing; fail if the state is stale

A record is the word of a team member on the project's own work. It qualifies
no flood map and is not an official approval.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import validation_records as vr  # noqa: E402

ITEMS = ROOT / "apps/web/src/lib/validation-check-items.json"
STATE = ROOT / "apps/web/src/lib/validation-check-records.json"
LOG = ROOT / "docs/validation/acceptance_records.jsonl"
REFUSED = ROOT / "docs/validation/refused_records.jsonl"
REVIEWERS = ROOT / "docs/validation/reviewers.json"
STATUS = ROOT / "docs/validation/STATUS.md"
LABEL = "validation-check"


def write_bytes(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))  # LF on every platform (.gitattributes, D-41)


def read_log(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def github_issues(repository: str) -> list[dict[str, Any]]:
    """Every issue with the label, oldest first, through the ``gh`` command."""

    completed = subprocess.run(
        ["gh", "issue", "list", "--repo", repository, "--label", LABEL, "--state", "all", "--limit", "500",
         "--json", "number,title,body,author,createdAt,url"],
        check=True, capture_output=True, text=True, encoding="utf-8",
    )
    return sorted(json.loads(completed.stdout), key=lambda issue: issue["createdAt"])


def take_in(text: str, *, source: dict[str, Any], received_at: str, login: str | None, items: dict[str, Any],
            reviewers: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return (stored record, None) for a record that counts, or (None, refusal) with the reasons."""

    def refusal(reasons: list[str]) -> dict[str, Any]:
        return {"record_id": vr.record_id(source, text), "received_at": received_at, "source": source, "reasons": reasons}

    try:
        record = vr.parse_record(text)
    except vr.ValidationRecordError as error:
        return None, refusal([str(error)])
    problems = vr.check_record(record, items)
    if source["kind"] == "github_issue":
        expected = (reviewers.get(record.reviewer) or {}).get("github")
        if not expected:
            problems.append(f"no GitHub account is listed for {record.reviewer}; hand the record over as a file")
        elif expected.lower() != (login or "").lower():
            problems.append(f"the issue was opened by {login!r}, not by the account listed for {record.reviewer}")
        identity = vr.IDENTITY_GITHUB
    else:
        identity = vr.IDENTITY_FILE
    if problems:
        return None, refusal(problems)
    return vr.stored_record(record, source=source, identity=identity, received_at=received_at, text=text), None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--github", action="store_true", help="read the issues labelled validation-check")
    parser.add_argument("--file", action="append", default=[], help="a record file handed over; may be given more than once")
    parser.add_argument("--check", action="store_true", help="write nothing; fail if the state file does not match the log")
    arguments = parser.parse_args()

    items = vr.load_items(ITEMS)
    reviewers = json.loads(REVIEWERS.read_text(encoding="utf-8"))["reviewers"]
    log = read_log(LOG)
    refused = read_log(REFUSED)
    known = {row["record_id"] for row in log} | {row["record_id"] for row in refused}

    if arguments.check:
        expected = vr.state_document(log, items, generated_at="-")
        current = json.loads(STATE.read_text(encoding="utf-8"))
        same = {**current, "generated_at_utc": "-"} == expected
        print("the state file matches the log" if same else "the state file is stale: run the import again")
        return 0 if same else 1

    incoming: list[tuple[str, dict[str, Any], str, str | None]] = []
    if arguments.github:
        for issue in github_issues(items["repository"].removeprefix("https://github.com/")):
            source = {"kind": "github_issue", "number": issue["number"], "url": issue["url"]}
            incoming.append((issue["body"] or "", source, issue["createdAt"], (issue.get("author") or {}).get("login")))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for name in arguments.file:
        path = Path(name)
        incoming.append((path.read_text(encoding="utf-8"), {"kind": "file", "file_name": path.name}, now, None))

    added = 0
    for text, source, received_at, login in incoming:
        if vr.record_id(source, text) in known:
            continue
        stored, refusal = take_in(text, source=source, received_at=received_at, login=login, items=items, reviewers=reviewers)
        if stored is not None:
            log.append(stored)
            added += 1
            print(f"counted: {stored['reviewer']}, {len(stored['decisions'])} decision(s), {source}")
        else:
            refused.append(refusal)
            print(f"refused: {source}: {'; '.join(refusal['reasons'])}")
        known.add(vr.record_id(source, text))

    write_bytes(LOG, "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in log))
    write_bytes(REFUSED, "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in refused))
    document = vr.state_document(log, items)
    write_bytes(STATE, json.dumps(document, indent=1, ensure_ascii=False) + "\n")
    write_bytes(STATUS, vr.status_markdown(document, items))
    print(f"{added} new record(s); {len(log)} counted in all; status: {document['status_counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
