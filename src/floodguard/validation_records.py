"""Team acceptance records of the validation-check page.

The page at ``/studio/validation-check/`` lists what the three team members
are asked to check. A reviewer records ``accept``, ``change`` or ``reject``
for each item and hands the record over as a short text, through a GitHub
issue or as a file. This module parses that text, checks it against the item
list and folds every record into one state per item.

A record is the word of a team member about the project's own work. It is not
a review by an independent expert, not a qualification of any flood map and
not an official approval; the statuses are named accordingly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

RECORD_HEADER = "floodguard-validation-record v1"
DECISIONS: tuple[str, ...] = ("accept", "change", "reject")
ITEMS_SCHEMA = "floodguard.validation_check.items.v1"
STATE_SCHEMA = "floodguard.validation_check.state.v1"
NOTE_MAX_CHARS = 300

STATUS_ACCEPTED = "accepted_by_all_reviewers"
STATUS_CHANGES = "changes_asked"
STATUS_WAITING = "waiting"
STATUS_NOT_READY = "evidence_not_ready"

IDENTITY_GITHUB = "github_login_matches_the_reviewer"
IDENTITY_FILE = "as_stated_in_a_file_handed_over_by_a_team_member"

_ITEM_ID = re.compile(r"^V-\d{2,3}$")
_DECISION_LINE = re.compile(r"^(V-\d{2,3})\s*:\s*([a-z]+)\s*(?:\|\s*(.*))?$")


class ValidationRecordError(ValueError):
    """The item list or a record is malformed."""


@dataclass(frozen=True)
class Decision:
    """One reviewer's word on one item."""

    item_id: str
    decision: str
    note: str = ""


@dataclass(frozen=True)
class Record:
    """One handed-over record: who, when by their own clock, and their decisions."""

    reviewer: str
    recorded_at: str
    decisions: tuple[Decision, ...]


def load_items(path: Path | str) -> dict[str, Any]:
    """Read and check the item list the page shows.

    Raises:
        ValidationRecordError: for a wrong schema, a repeated or malformed item
            ID, an unknown group, or a reviewer list that is not three names.
    """

    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if value.get("schema") != ITEMS_SCHEMA:
        raise ValidationRecordError(f"the item list must have the schema {ITEMS_SCHEMA}")
    reviewers = value.get("reviewers")
    if not isinstance(reviewers, list) or len(reviewers) != 3 or len(set(reviewers)) != 3:
        raise ValidationRecordError("the item list must name three distinct reviewers")
    groups = {group["id"] for group in value.get("groups", [])}
    seen: set[str] = set()
    for item in value.get("items", []):
        item_id = item.get("id", "")
        if not _ITEM_ID.match(item_id) or item_id in seen:
            raise ValidationRecordError(f"item IDs must be unique and look like V-01: {item_id!r}")
        seen.add(item_id)
        if item.get("group") not in groups:
            raise ValidationRecordError(f"{item_id} names an unknown group")
        for key in ("title", "check", "gates"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise ValidationRecordError(f"{item_id} needs a non-empty {key}")
        if not isinstance(item.get("ready"), bool):
            raise ValidationRecordError(f"{item_id} must say whether its evidence is ready")
    if not seen:
        raise ValidationRecordError("the item list is empty")
    return value


def clean_note(note: str) -> str:
    """Put a note on one line and cut it at the length the page allows."""

    return " ".join(str(note).replace("|", "/").split())[:NOTE_MAX_CHARS]


def format_record(record: Record) -> str:
    """Write a record as the text the page produces."""

    lines = [RECORD_HEADER, f"reviewer: {record.reviewer}", f"recorded_at: {record.recorded_at}"]
    for decision in record.decisions:
        note = clean_note(decision.note)
        lines.append(f"{decision.item_id}: {decision.decision}" + (f" | {note}" if note else ""))
    return "\n".join(lines) + "\n"


def parse_record(text: str) -> Record:
    """Read a record from the text of an issue or a file.

    Lines before the header are skipped, so a record pasted under a sentence
    still reads. A fenced code block around the record is allowed.

    Raises:
        ValidationRecordError: when the header, the reviewer or the time is
            missing, a line cannot be read, or an item is named twice.
    """

    lines = [line.strip() for line in str(text).replace("\r\n", "\n").split("\n")]
    lines = [line for line in lines if line and not line.startswith("```")]
    if RECORD_HEADER not in lines:
        raise ValidationRecordError("the text holds no validation record header")
    body = lines[lines.index(RECORD_HEADER) + 1:]
    fields: dict[str, str] = {}
    decisions: list[Decision] = []
    seen: set[str] = set()
    for line in body:
        match = _DECISION_LINE.match(line)
        if match:
            item_id, decision, note = match.group(1), match.group(2), match.group(3) or ""
            if decision not in DECISIONS:
                raise ValidationRecordError(f"{item_id}: the decision must be one of {', '.join(DECISIONS)}")
            if item_id in seen:
                raise ValidationRecordError(f"{item_id} is named twice in one record")
            seen.add(item_id)
            decisions.append(Decision(item_id, decision, clean_note(note)))
            continue
        key, separator, value = line.partition(":")
        if separator and key.strip() in ("reviewer", "recorded_at") and key.strip() not in fields:
            fields[key.strip()] = value.strip()
            continue
        raise ValidationRecordError(f"a line of the record cannot be read: {line[:60]!r}")
    if not fields.get("reviewer") or not fields.get("recorded_at"):
        raise ValidationRecordError("the record must name its reviewer and its time")
    try:
        datetime.fromisoformat(fields["recorded_at"].replace("Z", "+00:00"))
    except ValueError as error:
        raise ValidationRecordError("recorded_at must be an ISO 8601 time") from error
    if not decisions:
        raise ValidationRecordError("the record holds no decision")
    return Record(fields["reviewer"], fields["recorded_at"], tuple(decisions))


def check_record(record: Record, items: Mapping[str, Any]) -> list[str]:
    """Return what is wrong with a record against the item list; an empty list means it can be counted."""

    problems: list[str] = []
    if record.reviewer not in items["reviewers"]:
        problems.append(f"unknown reviewer {record.reviewer!r}")
    by_id = {item["id"]: item for item in items["items"]}
    for decision in record.decisions:
        item = by_id.get(decision.item_id)
        if item is None:
            problems.append(f"{decision.item_id} is not on the list")
        elif not item["ready"]:
            problems.append(f"{decision.item_id}: its evidence is not ready, so no decision is taken")
        if decision.decision != "accept" and not decision.note:
            problems.append(f"{decision.item_id}: a decision other than accept needs a note")
    return problems


def record_id(source: Mapping[str, Any], text: str) -> str:
    """A stable ID of one handed-over record: its source and its text."""

    payload = json.dumps({"source": dict(source), "text": text.replace("\r\n", "\n").strip()}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def stored_record(record: Record, *, source: Mapping[str, Any], identity: str, received_at: str, text: str) -> dict[str, Any]:
    """The line kept for a record in the append-only log."""

    return {
        "record_id": record_id(source, text),
        "received_at": received_at,
        "source": dict(source),
        "identity": identity,
        "reviewer": record.reviewer,
        "recorded_at": record.recorded_at,
        "decisions": [{"item_id": d.item_id, "decision": d.decision, "note": d.note} for d in record.decisions],
    }


def fold(records: Iterable[Mapping[str, Any]], items: Mapping[str, Any]) -> dict[str, Any]:
    """Fold every stored record into the state of each item.

    For each item and reviewer the record received last counts. An item whose
    evidence is not ready has no status but that. Otherwise it is accepted
    when all three reviewers accept it, has changes asked when any reviewer's
    current word is ``change`` or ``reject``, and waits in every other case.
    """

    reviewers = list(items["reviewers"])
    ordered = sorted(records, key=lambda row: (row["received_at"], row["record_id"]))
    latest: dict[str, dict[str, dict[str, Any]]] = {}
    for row in ordered:
        if row["reviewer"] not in reviewers:
            continue
        for decision in row["decisions"]:
            latest.setdefault(decision["item_id"], {})[row["reviewer"]] = {
                "decision": decision["decision"], "note": decision.get("note", ""),
                "received_at": row["received_at"], "record_id": row["record_id"],
            }
    state: dict[str, Any] = {}
    for item in items["items"]:
        words = latest.get(item["id"], {}) if item["ready"] else {}
        if not item["ready"]:
            status = STATUS_NOT_READY
        elif any(word["decision"] != "accept" for word in words.values()):
            status = STATUS_CHANGES
        elif all(reviewer in words for reviewer in reviewers):
            status = STATUS_ACCEPTED
        else:
            status = STATUS_WAITING
        state[item["id"]] = {
            "status": status,
            "accepted_by": sorted(name for name, word in words.items() if word["decision"] == "accept"),
            "by_reviewer": {reviewer: words.get(reviewer) for reviewer in reviewers},
        }
    return state


def state_document(records: Sequence[Mapping[str, Any]], items: Mapping[str, Any], *, generated_at: str | None = None) -> dict[str, Any]:
    """The file the page reads: the folded state, with what it is and is not."""

    state = fold(records, items)
    counts: dict[str, int] = {}
    for entry in state.values():
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    newest = max((row["received_at"] for row in records), default=None)
    return {
        "schema": STATE_SCHEMA,
        "generated_at_utc": generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_timestamp": newest,
        "confidence_class": "not_applicable",
        "what_this_is": "The word of the three team members on the project's own work, as handed over.",
        "assumptions": [
            "A record from a GitHub issue counts when its author is the account listed for the reviewer it names.",
            "A record from a file counts as stated; a team member handed the file over.",
            "For each item and reviewer the record received last counts.",
        ],
        "limits": [
            "It is not a review by an independent expert and qualifies no flood map.",
            "It is not an official approval and not an official warning.",
        ],
        "official_warning": False,
        "operational_status": "non_operational",
        "rule": items["rule"],
        "records_counted": len(records),
        "status_counts": dict(sorted(counts.items())),
        "items": state,
    }


def status_markdown(document: Mapping[str, Any], items: Mapping[str, Any]) -> str:
    """A table of the state, for the repository."""

    labels = {
        STATUS_ACCEPTED: "Accepted by all three", STATUS_CHANGES: "Changes asked",
        STATUS_WAITING: "Waiting", STATUS_NOT_READY: "Evidence not ready",
    }
    reviewers = list(items["reviewers"])
    lines = [
        "# Validation check: state of the team's acceptance",
        "",
        f"Written by `scripts/import_validation_records.py` on {document['generated_at_utc']} from "
        f"{document['records_counted']} record(s). Do not edit by hand.",
        "",
        "This is the word of the three team members on the project's own work. It is not a review by an "
        "independent expert, it qualifies no flood map, and it is not an official approval.",
        "",
        "| Item | What | Status | " + " | ".join(reviewers) + " |",
        "|---|---|---|" + "---|" * len(reviewers),
    ]
    for item in items["items"]:
        entry = document["items"][item["id"]]
        cells = []
        for reviewer in reviewers:
            word = entry["by_reviewer"][reviewer]
            cells.append("" if word is None else word["decision"] + (f": {word['note']}" if word["note"] else ""))
        lines.append(f"| {item['id']} | {item['title']} | {labels[entry['status']]} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"
