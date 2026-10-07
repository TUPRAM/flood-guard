"""Tests of the acceptance records of the validation-check page."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from floodguard import validation_records as vr

ROOT = Path(__file__).resolve().parents[1]
ITEMS_PATH = ROOT / "apps/web/src/lib/validation-check-items.json"
STATE_PATH = ROOT / "apps/web/src/lib/validation-check-records.json"
LOG_PATH = ROOT / "docs/validation/acceptance_records.jsonl"

ITEMS = {
    "schema": vr.ITEMS_SCHEMA,
    "reviewers": ["Rachmania", "Putu", "Callixta"],
    "rule": "all three",
    "groups": [{"id": "g", "title": "Group"}],
    "items": [
        {"id": "V-01", "group": "g", "title": "One", "check": "c", "gates": "g", "ready": True},
        {"id": "V-02", "group": "g", "title": "Two", "check": "c", "gates": "g", "ready": True},
        {"id": "V-03", "group": "g", "title": "Three", "check": "c", "gates": "g", "ready": False},
    ],
}


def _stored(reviewer: str, received: str, *decisions: tuple[str, str, str]) -> dict:
    record = vr.Record(reviewer, received, tuple(vr.Decision(*decision) for decision in decisions))
    return vr.stored_record(record, source={"kind": "file", "file_name": f"{reviewer}-{received}.txt"},
                            identity=vr.IDENTITY_FILE, received_at=received, text=vr.format_record(record))


def test_record_text_round_trip_keeps_decisions_and_cleans_notes() -> None:
    record = vr.Record("Putu", "2026-10-07T09:00:00Z", (
        vr.Decision("V-01", "accept"), vr.Decision("V-02", "change", "line one\nline | two"),
    ))
    text = vr.format_record(record)
    assert text.splitlines()[0] == vr.RECORD_HEADER
    parsed = vr.parse_record("Here is my record:\n```\n" + text + "```\n")
    assert parsed.reviewer == "Putu"
    assert [(d.item_id, d.decision, d.note) for d in parsed.decisions] == [
        ("V-01", "accept", ""), ("V-02", "change", "line one line / two")]


@pytest.mark.parametrize("text, message", [
    ("reviewer: Putu\nV-01: accept", "header"),
    (vr.RECORD_HEADER + "\nreviewer: Putu\nrecorded_at: 2026-10-07T09:00:00Z\nV-01: maybe", "decision must be"),
    (vr.RECORD_HEADER + "\nreviewer: Putu\nrecorded_at: 2026-10-07T09:00:00Z\nV-01: accept\nV-01: reject | x", "twice"),
    (vr.RECORD_HEADER + "\nreviewer: Putu\nrecorded_at: yesterday\nV-01: accept", "ISO 8601"),
    (vr.RECORD_HEADER + "\nreviewer: Putu\nrecorded_at: 2026-10-07T09:00:00Z", "no decision"),
    (vr.RECORD_HEADER + "\nrecorded_at: 2026-10-07T09:00:00Z\nV-01: accept", "reviewer"),
    (vr.RECORD_HEADER + "\nreviewer: Putu\nrecorded_at: 2026-10-07T09:00:00Z\nsomething else", "cannot be read"),
])
def test_malformed_records_are_refused(text: str, message: str) -> None:
    with pytest.raises(vr.ValidationRecordError, match=message):
        vr.parse_record(text)


def test_check_record_names_every_problem() -> None:
    record = vr.Record("Someone", "2026-10-07T09:00:00Z", (
        vr.Decision("V-01", "reject"), vr.Decision("V-03", "accept"), vr.Decision("V-99", "accept"),
    ))
    problems = vr.check_record(record, ITEMS)
    assert any("unknown reviewer" in problem for problem in problems)
    assert any("V-01" in problem and "needs a note" in problem for problem in problems)
    assert any("V-03" in problem and "not ready" in problem for problem in problems)
    assert any("V-99" in problem and "not on the list" in problem for problem in problems)
    assert vr.check_record(vr.Record("Putu", "2026-10-07T09:00:00Z", (vr.Decision("V-01", "accept"),)), ITEMS) == []


def test_fold_one_acceptance_is_enough_a_change_holds_and_the_last_word_counts() -> None:
    assert vr.fold([], ITEMS)["V-01"]["status"] == vr.STATUS_WAITING
    records = [_stored("Putu", "2026-10-07T09:00:00Z", ("V-01", "accept", ""), ("V-02", "accept", ""))]
    state = vr.fold(records, ITEMS)
    # One acceptance is enough (decision log R28).
    assert state["V-01"]["status"] == vr.STATUS_ACCEPTED
    assert state["V-01"]["accepted_by"] == ["Putu"]
    records += [
        _stored("Callixta", "2026-10-07T10:00:00Z", ("V-01", "accept", ""), ("V-02", "change", "reword")),
        _stored("Rachmania", "2026-10-07T11:00:00Z", ("V-01", "accept", "")),
    ]
    state = vr.fold(records, ITEMS)
    assert state["V-01"]["accepted_by"] == ["Callixta", "Putu", "Rachmania"]
    # One change holds the item, whatever the others said.
    assert state["V-02"]["status"] == vr.STATUS_CHANGES
    assert state["V-02"]["accepted_by"] == ["Putu"]
    assert state["V-03"]["status"] == vr.STATUS_NOT_READY
    # A later record of the same reviewer replaces the earlier word.
    records.append(_stored("Callixta", "2026-10-07T12:00:00Z", ("V-02", "accept", "")))
    state = vr.fold(records, ITEMS)
    assert state["V-02"]["status"] == vr.STATUS_ACCEPTED
    assert state["V-02"]["by_reviewer"]["Rachmania"] is None
    # The order of the list does not matter: only the time received does.
    assert vr.fold(list(reversed(records)), ITEMS) == state


def test_a_record_for_an_item_that_is_not_ready_changes_nothing() -> None:
    state = vr.fold([_stored("Putu", "2026-10-07T09:00:00Z", ("V-03", "accept", ""))], ITEMS)
    assert state["V-03"] == {"status": vr.STATUS_NOT_READY, "accepted_by": [],
                             "by_reviewer": {"Rachmania": None, "Putu": None, "Callixta": None}}


def test_record_id_depends_on_source_and_text_not_on_line_ends() -> None:
    source = {"kind": "github_issue", "number": 5, "url": "u"}
    assert vr.record_id(source, "a\r\nb\n") == vr.record_id(source, "a\nb")
    assert vr.record_id(source, "a") != vr.record_id({**source, "number": 6}, "a")


def test_state_document_carries_the_required_fields_and_says_what_it_is_not() -> None:
    document = vr.state_document([_stored("Putu", "2026-10-07T09:00:00Z", ("V-01", "accept", ""))], ITEMS,
                                 generated_at="2026-10-07T12:00:00Z")
    assert document["official_warning"] is False
    assert document["operational_status"] == "non_operational"
    assert document["source_timestamp"] == "2026-10-07T09:00:00Z"
    assert document["assumptions"] and document["limits"]
    assert document["status_counts"] == {vr.STATUS_ACCEPTED: 1, vr.STATUS_NOT_READY: 1, vr.STATUS_WAITING: 1}
    table = vr.status_markdown(document, ITEMS)
    assert "| V-01 | One | Accepted |  | accept |  |" in table
    assert "not a review by an independent expert" in table


@pytest.mark.parametrize("change, message", [
    ({"schema": "other"}, "schema"),
    ({"reviewers": ["A", "B"]}, "three distinct reviewers"),
    ({"items": [{**ITEMS["items"][0]}, {**ITEMS["items"][0]}]}, "unique"),
    ({"items": [{**ITEMS["items"][0], "group": "missing"}]}, "unknown group"),
    ({"items": [{**ITEMS["items"][0], "ready": "yes"}]}, "ready"),
    ({"items": []}, "empty"),
])
def test_a_malformed_item_list_is_refused(tmp_path: Path, change: dict, message: str) -> None:
    path = tmp_path / "items.json"
    path.write_text(json.dumps({**ITEMS, **change}), encoding="utf-8")
    with pytest.raises(vr.ValidationRecordError, match=message):
        vr.load_items(path)


def test_the_committed_item_list_is_well_formed_and_points_at_real_files() -> None:
    items = vr.load_items(ITEMS_PATH)
    assert items["reviewers"] == ["Rachmania", "Putu", "Callixta"]
    for item in items["items"]:
        if item["ready"]:
            assert item["evidence"], f"{item['id']} is ready and names no evidence"
        for evidence in item["evidence"]:
            assert ("path" in evidence) != ("href" in evidence)
            if "path" in evidence:
                assert (ROOT / evidence["path"]).is_file(), f"{item['id']}: {evidence['path']} does not exist"
            else:
                assert evidence["href"].startswith("/") and evidence["href"].endswith("/")


def test_the_committed_state_is_the_fold_of_the_committed_log() -> None:
    items = vr.load_items(ITEMS_PATH)
    log = [json.loads(line) for line in LOG_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    current = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    expected = vr.state_document(log, items, generated_at=current["generated_at_utc"])
    assert current == expected


def test_the_importer_checks_the_github_account_of_a_record() -> None:
    spec = importlib.util.spec_from_file_location("import_validation_records", ROOT / "scripts/import_validation_records.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    reviewers = {"Putu": {"github": "TUPRAM"}, "Rachmania": {"github": None}, "Callixta": {"github": "callixtafidelia"}}
    text = vr.format_record(vr.Record("Putu", "2026-10-07T09:00:00Z", (vr.Decision("V-01", "accept"),)))
    source = {"kind": "github_issue", "number": 1, "url": "u"}
    stored, refusal = module.take_in(text, source=source, received_at="2026-10-07T09:01:00Z", login="tupram",
                                     items=ITEMS, reviewers=reviewers)
    assert refusal is None and stored["identity"] == vr.IDENTITY_GITHUB
    stored, refusal = module.take_in(text, source=source, received_at="2026-10-07T09:01:00Z", login="stranger",
                                     items=ITEMS, reviewers=reviewers)
    assert stored is None and "not by the account listed" in refusal["reasons"][0]
    other = vr.format_record(vr.Record("Rachmania", "2026-10-07T09:00:00Z", (vr.Decision("V-01", "accept"),)))
    stored, refusal = module.take_in(other, source=source, received_at="2026-10-07T09:01:00Z", login="anyone",
                                     items=ITEMS, reviewers=reviewers)
    assert stored is None and "hand the record over as a file" in refusal["reasons"][0]
    stored, refusal = module.take_in(other, source={"kind": "file", "file_name": "r.txt"},
                                     received_at="2026-10-07T09:01:00Z", login=None, items=ITEMS, reviewers=reviewers)
    assert refusal is None and stored["identity"] == vr.IDENTITY_FILE
