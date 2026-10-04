"""Check a signed planning protocol file and print its RECEIPTS.jsonl line.

Agents draft, humans sign. This script signs nothing, edits no protocol file
and never writes ``RECEIPTS.jsonl``: it prints one JSON line that a signer
reads and appends by hand. It computes no FPPS, no A-E class and no ensemble.

Run it from the repository root, on the clean signing commit::

    python scripts/record_planning_protocol_receipt.py v1a
    python scripts/record_planning_protocol_receipt.py v1b

It refuses to print unless the committed file is signed by two different
people, validates against its schema, has every drafter reading resolved and,
for v1b, has every open item closed, every named parameter filled in and the
recorded v1a hash. It runs the protocol and scoring tests itself.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Iterable, Sequence

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
DOCS = "docs/proposal_execution"
RECEIPTS_PATH = f"{DOCS}/RECEIPTS.jsonl"
SCORING_PATH = "src/floodguard/scoring.py"
RECEIPT_SCHEMA_VERSION = "floodguard.proposal_execution_receipt.v1"
PROTOCOL_NAMES = ("v1a", "v1b")
TEST_PATHS = (
    "tests/test_planning_protocol.py",
    "tests/test_scoring.py",
    "tests/test_scoring_sensitivity.py",
)
AWAITING = "awaiting_owner_confirmation"
SIGNER_FIRST_NAMES = ("Putu", "Rachmania")


def protocol_path(name: str) -> str:
    """Return the repository-relative path of a protocol file."""

    return f"{DOCS}/planning_protocol_{name}.json"


def schema_path(name: str) -> str:
    """Return the repository-relative path of a protocol schema."""

    return f"{DOCS}/planning_protocol_{name}.schema.json"


def sha256_hex(data: bytes) -> str:
    """Return the SHA-256 of bytes as lowercase hex."""

    return hashlib.sha256(data).hexdigest()


def resolve_pointer(document: Any, pointer: str) -> Any:
    """Return the value at a JSON pointer (RFC 6901, without escapes).

    Raises:
        KeyError, IndexError or ValueError when the pointer does not resolve.
    """

    node = document
    for part in pointer.lstrip("/").split("/"):
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def parse_receipts(text: str) -> list[dict[str, Any]]:
    """Parse the lines of RECEIPTS.jsonl."""

    return [json.loads(line) for line in text.splitlines() if line.strip()]


def recorded_protocol_hashes(receipts: Iterable[dict[str, Any]], name: str) -> list[dict[str, str]]:
    """List every receipt that records a hash for one protocol file, oldest first."""

    key = f"planning_protocol_{name}_sha256"
    found = []
    for receipt in receipts:
        outputs = receipt.get("output_hashes")
        if isinstance(outputs, dict) and key in outputs:
            found.append({"sha256": str(outputs[key]), "source_commit": str(receipt.get("source_commit", ""))})
    return found


def force_state(name: str, protocol_bytes: bytes, receipts: Iterable[dict[str, Any]]) -> str:
    """Say whether a protocol file is in force.

    Returns:
        ``draft``: not signed and no receipt.
        ``signed_not_in_force``: status is signed but no receipt records its hash.
        ``in_force``: signed, and every recorded hash equals the SHA-256 of these bytes.
        ``hash_mismatch``: a receipt exists, but the bytes or the status do not match it.
    """

    status = json.loads(protocol_bytes.decode("utf-8")).get("status")
    recorded = recorded_protocol_hashes(receipts, name)
    if recorded:
        matches = {entry["sha256"] for entry in recorded} == {sha256_hex(protocol_bytes)}
        return "in_force" if matches and status == "signed" else "hash_mismatch"
    return "signed_not_in_force" if status == "signed" else "draft"


def empty_parameters(v1b: dict[str, Any], *, closed_only: bool = False) -> list[str]:
    """List the parameter pointers of v1b open items that are missing or null.

    Args:
        v1b: The parsed v1b protocol.
        closed_only: Look only at items whose status is ``closed``.
    """

    empty = []
    for item in v1b.get("open_items", []):
        if closed_only and item.get("status") != "closed":
            continue
        for pointer in item.get("parameter_pointers", []):
            try:
                value = resolve_pointer(v1b, pointer)
            except (KeyError, IndexError, ValueError):
                value = None
            if value is None:
                empty.append(f"{item['id']}: {pointer}")
    return empty


def signing_problems(
    name: str,
    protocol_bytes: bytes,
    schema: dict[str, Any],
    *,
    receipts: Sequence[dict[str, Any]] = (),
    v1a_bytes: bytes | None = None,
) -> list[str]:
    """List everything that stops a protocol file from being recorded.

    An empty list means the file may be recorded. The checks need no git.

    Args:
        name: ``v1a`` or ``v1b``.
        protocol_bytes: The committed bytes of the protocol file.
        schema: The parsed schema for that file.
        receipts: The parsed lines of RECEIPTS.jsonl.
        v1a_bytes: The committed bytes of v1a; required when ``name`` is ``v1b``.
    """

    problems: list[str] = []
    if b"\r" in protocol_bytes or not protocol_bytes.endswith(b"\n") or protocol_bytes.endswith(b"\n\n"):
        problems.append("the file must use LF line endings and end with exactly one newline")
    protocol = json.loads(protocol_bytes.decode("utf-8"))

    if protocol.get("status") != "signed":
        problems.append(f"status is {protocol.get('status')!r}, not 'signed'")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for error in validator.iter_errors(protocol):
        where = "/".join(str(part) for part in error.path) or "(root)"
        problems.append(f"schema: {where}: {error.message[:200]}")

    signers = protocol.get("signature_block", {}).get("signers", [])
    names = [str(signer.get("signed_by") or "").strip() for signer in signers]
    if len(names) != 2 or not all(names):
        problems.append("both signature entries must be filled in")
    else:
        if names[0].casefold() == names[1].casefold():
            problems.append("the two signed_by values are the same; two different people must sign")
        for expected, given in zip(SIGNER_FIRST_NAMES, names):
            if expected.casefold() not in given.casefold():
                problems.append(f"signed_by {given!r} does not name the required signer {expected}")

    awaiting = [entry["id"] for entry in protocol.get("drafter_readings", []) if entry.get("status") == AWAITING]
    if awaiting:
        problems.append(f"drafter readings still await owner confirmation: {', '.join(awaiting)}")

    if recorded_protocol_hashes(receipts, name):
        problems.append(
            f"RECEIPTS.jsonl already records a hash for {name}; a recorded protocol is not edited or recorded "
            "again, and any change needs planning_protocol_v2"
        )

    if name == "v1b":
        still_open = [item["id"] for item in protocol.get("open_items", []) if item.get("status") != "closed"]
        if still_open:
            problems.append(f"open items are not closed: {', '.join(still_open)}")
        empty = empty_parameters(protocol)
        if empty:
            problems.append(f"parameters named by open items are empty: {'; '.join(empty)}")
        if v1a_bytes is None:
            problems.append("the committed v1a file is needed to check depends_on.v1a_sha256")
        else:
            declared = protocol.get("depends_on", {}).get("v1a_sha256")
            if declared != sha256_hex(v1a_bytes):
                problems.append("depends_on.v1a_sha256 is not the SHA-256 of the committed v1a file")
            state = force_state("v1a", v1a_bytes, receipts)
            if state != "in_force":
                problems.append(f"v1a is not in force (state: {state}); record v1a before v1b")
            recorded = recorded_protocol_hashes(receipts, "v1a")
            if recorded and declared != recorded[-1]["sha256"]:
                problems.append("depends_on.v1a_sha256 is not the value in the v1a receipt line")
    return problems


def build_receipt(
    name: str,
    *,
    commit: str,
    tree: str,
    protocol_sha256: str,
    input_hashes: dict[str, str],
    test_summary: str,
    signed_by: Sequence[str],
    open_decisions: Sequence[str],
    time_utc: str,
) -> dict[str, Any]:
    """Build the receipt object, with the keys the existing receipts use."""

    path = protocol_path(name)
    test_command = "python -m pytest -q " + " ".join(TEST_PATHS)
    open_text = ", ".join(open_decisions) if open_decisions else "none"
    next_step = (
        "Close the v1b open items, then sign and record v1b. No FPPS, A-E class or ensemble before the v1b receipt."
        if name == "v1a"
        else "Planning-tier scoring may start. Any change to v1a or v1b needs planning_protocol_v2."
    )
    return {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "time_utc": time_utc,
        "result": "PASS",
        "source_commit": commit,
        "source_tree": tree,
        "source_state": (
            "Clean signing commit: git status --porcelain was empty when this line was built. The protocol bytes "
            "are those of this commit; this receipt line is added in the next commit."
        ),
        "input_hashes": input_hashes,
        "output_hashes": {f"planning_protocol_{name}_sha256": protocol_sha256},
        "commands_actually_run": [
            f"python scripts/record_planning_protocol_receipt.py {name}",
            f"{test_command} (run by the script)",
            f"git show {commit}:{path} (hashed as bytes by the script)",
        ],
        "command_record_status": "PASS",
        "tests_or_checks": [
            f"Protocol and scoring tests, run by the script: {test_summary}",
            "Working tree clean; committed protocol bytes equal the working file",
            "Schema valid; two different signers; every drafter reading confirmed or amended",
            *(
                ["Every open item closed with its parameters filled; depends_on.v1a_sha256 equals the v1a receipt"]
                if name == "v1b"
                else []
            ),
        ],
        "scientific_acceptance": False,
        "human_acceptance": False,
        "official_warning": False,
        "operational_status": "non_operational",
        "milestone": f"P0-{name}",
        "scientific_evidence": (
            "None. A declared protocol after exploratory analysis. No planning-tier FPPS, A-E class or ensemble "
            "exists at this receipt."
        ),
        "human_evidence": (
            f"Team governance signature recorded in the file's signature block by {' and '.join(signed_by)}. "
            "Not an independent review. The file cannot prove who typed a name."
        ),
        "limitations": (
            "Rules were declared after exploratory analysis, as disclosed in v1a. "
            f"Open decisions at this receipt: {open_text}."
        ),
        "next_dependencies": next_step,
        "eligible_claim": f"Planning protocol {name} is signed and its committed bytes are bound by SHA-256.",
    }


def _git(*args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True).stdout


def _fail(messages: Iterable[str]) -> int:
    for message in messages:
        sys.stderr.write(f"REFUSED: {message}\n")
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    """Check the signing commit and print one receipt line. Returns a process exit code."""

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("name", choices=PROTOCOL_NAMES, help="which protocol file to record")
    name = parser.parse_args(argv).name

    dirty = _git("status", "--porcelain").decode("utf-8", "replace").strip()
    if dirty:
        return _fail(["the working tree is not clean; commit the signed file first", dirty])

    commit = _git("rev-parse", "HEAD").decode().strip()
    tree = _git("rev-parse", "HEAD^{tree}").decode().strip()

    def committed(path: str) -> bytes:
        return _git("show", f"{commit}:{path}")

    protocol_bytes = committed(protocol_path(name))
    if protocol_bytes != (ROOT / protocol_path(name)).read_bytes():
        return _fail(["the working file differs from the committed bytes (check line-ending settings)"])
    schema_bytes = committed(schema_path(name))
    receipts = parse_receipts(committed(RECEIPTS_PATH).decode("utf-8"))
    v1a_bytes = committed(protocol_path("v1a"))

    problems = signing_problems(
        name,
        protocol_bytes,
        json.loads(schema_bytes.decode("utf-8")),
        receipts=receipts,
        v1a_bytes=v1a_bytes if name == "v1b" else None,
    )
    if problems:
        return _fail(problems)

    tests = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *TEST_PATHS], cwd=ROOT, capture_output=True, text=True
    )
    lines = [line for line in tests.stdout.splitlines() if line.strip()]
    summary = re.sub(r"\s+", " ", lines[-1]).strip() if lines else "no output"
    if tests.returncode != 0:
        return _fail([f"the tests did not pass: {summary}", tests.stdout[-2000:]])
    if _git("status", "--porcelain").decode("utf-8", "replace").strip():
        return _fail(["running the tests changed the working tree"])

    input_hashes = {
        f"planning_protocol_{name}_schema_sha256": sha256_hex(schema_bytes),
        "scoring_py_sha256": sha256_hex(committed(SCORING_PATH)),
    }
    if name == "v1b":
        input_hashes["planning_protocol_v1a_sha256"] = sha256_hex(v1a_bytes)
    protocol = json.loads(protocol_bytes.decode("utf-8"))
    v1a = json.loads(v1a_bytes.decode("utf-8"))
    receipt = build_receipt(
        name,
        commit=commit,
        tree=tree,
        protocol_sha256=sha256_hex(protocol_bytes),
        input_hashes=input_hashes,
        test_summary=summary,
        signed_by=[signer["signed_by"] for signer in protocol["signature_block"]["signers"]],
        open_decisions=[decision["id"] for decision in v1a.get("open_decisions", []) if decision.get("status") == "open"],
        time_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    line = json.dumps(receipt, separators=(",", ":"), ensure_ascii=False)
    sys.stdout.buffer.write(line.encode("utf-8") + b"\n")  # raw bytes: one line, one LF, no CR on Windows
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
