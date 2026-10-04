"""Guard for the AIT and MBRSC flood products (planning protocol v1a, guardrail ``GR9_ait_mbrsc_guard``).

The guardrail: "A pre-commit test must fail if any committed script reads AIT-VAP001 or MBRSC paths without a
recorded grant receipt. No AIT or MBRSC number appears in committed code or on any public surface." (plan
section 0 item 3, section 2.3 item 9 and row 8.1 A1.) Neither product may be processed until its provider
grants it: the AIT product is a Sentinel Asia value-added product, and the MBRSC map is held blocked by
``docs/mbrsc_reference_mask_clearance_memo.md``.

What this module checks, and how far it reaches:

1. **Paths** (:func:`path_findings`). Every code file of the repository is searched for a name of the two
   products or of their folders. A file that names one fails unless (a) it is a **legacy** file, listed in
   ``docs/proposal_execution/ait_mbrsc_guard_baseline_v1.json`` with the SHA-256 of the lines that name the
   product, so that a new or changed line fails too, or (b) a **grant** for that product is recorded.
2. **Numbers** (:func:`number_findings`). In the files of the diagnosis (plan task A1), a line that names
   AIT or MBRSC may hold no figure. The check is limited to those files: no automated test can tell which
   number elsewhere in the repository was derived from the two products.

The guard cannot see a script that reads the products without naming them, for example through a folder
listing. It is a net for the usual case, not a proof.

**What a grant is** is not stated by the signed files: the guardrail says "a recorded grant receipt" and
gives neither its form nor its place (open point A1-OP7). This module reads the one place where the
repository records rights: the registry of :mod:`floodguard.rights`. A product is granted when the registry
holds a record of that source (:data:`GRANT_SOURCES`) that its owners confirmed and a human signed. No such
record exists today, so nothing is granted.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any

from floodguard import rights

GUARDRAIL = "GR9_ait_mbrsc_guard"
BASELINE_PATH = Path("docs") / "proposal_execution" / "ait_mbrsc_guard_baseline_v1.json"
BASELINE_SCHEMA = "floodguard.ait_mbrsc_guard_baseline.v1"

AIT = "ait"
MBRSC = "mbrsc"
GRANT_SOURCES: Mapping[str, str] = {AIT: "sentinel_asia_ait_vap001", MBRSC: "sentinel_asia_mbrsc"}
"""The kind of source data (``RegisteredRecord.source``) a grant of each product is a record of."""

SOURCE_PATTERNS: Mapping[str, re.Pattern[str]] = {
    AIT: re.compile(r"ait[-_ ]?vap|vap[-_ ]?001|sentinel_asia_ait|reference_candidates[/\\]+sentinel_asia", re.IGNORECASE),
    MBRSC: re.compile(r"mbrsc[-_](?!guard)[a-z0-9]|[-_/\\]mbrsc(?!_guard)", re.IGNORECASE),
}
"""What names each product in code: its product identifier or file name, or its folder in the external data workspace.
The bare words AIT and MBRSC in a sentence are not a path and are not matched here, and neither is the name of
this guard (``ait_mbrsc_guard``)."""

SHARED_FOLDER_PATTERN = re.compile(r"sentinel_asia(?!_ait)", re.IGNORECASE)
"""The external folder that holds the MBRSC archive and other Sentinel Asia files; naming it names both products."""

CODE_SUFFIXES = frozenset({".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".sh", ".ps1", ".bat", ".ipynb"})
"""A committed script is any tracked file with one of these suffixes."""

GUARD_FILES = frozenset({
    "src/floodguard/ait_mbrsc_guard.py",
    "scripts/check_ait_mbrsc_guard.py",
    "tests/test_ait_mbrsc_guard.py",
})
"""The guard, its command and its test name the products in order to look for them; they read no product file."""

A1_FILE_PATTERNS: tuple[str, ...] = (
    "scripts/diagnostics/*",
    "outputs/a1_diagnosis/*",
    "outputs/planning_v1/a1_diagnosis_*.json",
    "docs/proposal_execution/automated_track/WHY_THRESHOLD_ONLY_FAILED.md",
    "src/floodguard/abstention_diagnosis.py",
    "src/floodguard/diagnosis_run.py",
    "src/floodguard/diagnosis_layers.py",
)
"""The files of plan task A1, in which a line that names AIT or MBRSC may hold no figure."""

PRODUCT_WORD = re.compile(r"(?<![A-Za-z])(?:AIT|MBRSC)(?![A-Za-z])")
_NOT_A_FIGURE = re.compile(
    r"AIT[-_ ]?VAP[-_ ]?\d+(?:-TH)?|[A-Z]\d-OP\d+|EK-\d+|ALOS-2|Sentinel-[12]|SHA-?256|(?:product\s+)?4009"
    r"|(?<![A-Za-z0-9.])[A-Za-z]{1,2}\d{1,2}[a-z]?(?![A-Za-z0-9])(?!\.\d)"
    r"|(?:plan|section|row|item|rule|line|lines)\s+[0-9][0-9.]*(?:\s+item\s+\d+)?"
    r"|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*(?:\s+\d{4})?|(?<![0-9.])(?:19|20)\d{2}(?![0-9])(?!\.\d)",
    re.IGNORECASE,
)
"""Identifiers and dates that hold digits and are not figures: product names, rule and decision numbers (GR9, A1,
v1a, D12), plan sections, the product number 4009 and dates."""


class GuardError(ValueError):
    """Raised when the baseline of the guard is missing or malformed."""


@dataclass(frozen=True)
class Finding:
    """One thing the guard refuses: a file, what it names and why that is not allowed."""

    path: str
    kind: str
    products: tuple[str, ...]
    detail: str

    def describe(self) -> str:
        """Return the finding as one line."""

        return f"{self.path}: {self.kind} ({', '.join(self.products)}): {self.detail}"


def naming_lines(text: str) -> dict[str, list[str]]:
    """Return, for each product, the lines of ``text`` that name it or its folder, stripped of outer white space."""

    found: dict[str, list[str]] = {AIT: [], MBRSC: []}
    for line in text.splitlines():
        shared = SHARED_FOLDER_PATTERN.search(line) is not None
        for product, pattern in SOURCE_PATTERNS.items():
            if shared or pattern.search(line):
                found[product].append(line.strip())
    return {product: lines for product, lines in found.items() if lines}


def lines_digest(lines_by_product: Mapping[str, Sequence[str]]) -> str:
    """Return the SHA-256 of the naming lines of a file, so that a new or changed line is noticed."""

    lines = sorted({line for lines in lines_by_product.values() for line in lines})
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def repository_files(root: Path) -> list[str]:
    """Return the files Git tracks and the new files it does not ignore, as repository paths.

    A pre-commit run must see a file before it is committed, so untracked files that are not ignored count.
    Outside a Git checkout every file under the root is returned.
    """

    try:
        tracked = subprocess.run(["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True).stdout
        new = subprocess.run(["git", "ls-files", "-z", "--others", "--exclude-standard"], cwd=root, check=True,
                             capture_output=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())
    return sorted({name for name in (tracked + new).decode("utf-8").split("\0") if name})


def code_files(files: Iterable[str]) -> list[str]:
    """Return the committed scripts among ``files``: every file with a code suffix."""

    return sorted(name for name in files if Path(name).suffix.lower() in CODE_SUFFIXES)


def load_baseline(root: Path) -> dict[str, dict[str, Any]]:
    """Read the legacy files of the baseline: path to the SHA-256 of its naming lines and the products it names.

    Raises:
        GuardError: when the baseline is missing or is not in the schema this module reads.
    """

    path = root / BASELINE_PATH
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise GuardError(f"the baseline of the guard is missing: {BASELINE_PATH.as_posix()}") from error
    files = document.get("files")
    if document.get("schema") != BASELINE_SCHEMA or not isinstance(files, dict):
        raise GuardError("the baseline of the guard is not in the schema this module reads")
    for name, entry in files.items():
        if not isinstance(entry, dict) or not re.fullmatch(r"[0-9a-f]{64}", str(entry.get("naming_lines_sha256", ""))) \
                or not set(entry.get("products", [])) <= set(GRANT_SOURCES) or not entry.get("products"):
            raise GuardError(f"the baseline entry of {name} needs the SHA-256 of its naming lines and its products")
    return files


def recorded_grants(registry: rights.RightsRegistry, records: Sequence[rights.RegisteredRecord] = rights.REGISTERED_RECORDS) -> dict[str, str]:
    """Return the products for which a grant is recorded, each with the path of its confirmed record.

    A product is granted when a registered rights record is a record of its source and the registry accepts
    the use: the record exists, a human signed it and the owners confirmed it.
    """

    granted: dict[str, str] = {}
    for product, source in GRANT_SOURCES.items():
        for entry in records:
            if entry.source != source:
                continue
            try:
                grant = registry.require_use(entry.input_id, source=source)
            except rights.rights_basis.RightsBasisError:
                continue
            granted[product] = grant.record_path
    return granted


def path_findings(root: Path, files: Iterable[str], baseline: Mapping[str, Mapping[str, Any]], grants: Mapping[str, str]) -> list[Finding]:
    """Return every committed script that names a product it may not read.

    A file passes when it names no product, when it is one of the guard's own files, when it is a legacy file
    whose naming lines are those of the baseline, or when every product it names is granted.
    """

    findings: list[Finding] = []
    for name in code_files(files):
        if name in GUARD_FILES:
            continue
        try:
            text = (root / name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        naming = naming_lines(text)
        if not naming:
            continue
        missing = tuple(sorted(product for product in naming if product not in grants))
        if not missing:
            continue
        entry = baseline.get(name)
        if entry is None:
            findings.append(Finding(name, "names_a_product_without_a_grant", missing,
                                    "no grant is recorded and the file is not a legacy file of the baseline"))
        elif entry["naming_lines_sha256"] != lines_digest(naming):
            findings.append(Finding(name, "legacy_file_changed", missing,
                                    "the lines that name the product are not those the baseline records"))
    return findings


def _matches(name: str, patterns: Sequence[str]) -> bool:
    return any(Path(name).match(pattern) for pattern in patterns)


def figure_in_line(line: str) -> bool:
    """Say whether a line that names AIT or MBRSC also holds a figure.

    Product identifiers, rule and section numbers, years and dates are not figures. Any other digit is.
    """

    if not PRODUCT_WORD.search(line):
        return False
    return re.search(r"\d", _NOT_A_FIGURE.sub(" ", line)) is not None


def number_findings(root: Path, files: Iterable[str], patterns: Sequence[str] = A1_FILE_PATTERNS) -> list[Finding]:
    """Return every line of the diagnosis files that names AIT or MBRSC and holds a figure."""

    findings: list[Finding] = []
    for name in sorted(files):
        if not _matches(name, patterns):
            continue
        try:
            text = (root / name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if figure_in_line(line):
                products = tuple(sorted({word.lower() for word in PRODUCT_WORD.findall(line)}))
                findings.append(Finding(name, "figure_beside_a_product_name", products, f"line {number}: {line.strip()[:160]}"))
    return findings


def check(root: Path, *, registry: rights.RightsRegistry | None = None) -> dict[str, Any]:
    """Run both checks on a checkout and return what was looked at and what was refused."""

    files = repository_files(root)
    baseline = load_baseline(root)
    grants = recorded_grants(registry or rights.RightsRegistry(root))
    findings = path_findings(root, files, baseline, grants) + number_findings(root, files)
    return {
        "guardrail": GUARDRAIL,
        "code_files_searched": len(code_files(files)),
        "legacy_files_in_the_baseline": len(baseline),
        "grants_recorded": dict(grants),
        "findings": [finding.describe() for finding in findings],
        "passed": not findings,
    }


def build_baseline(root: Path, *, recorded_on: str) -> dict[str, Any]:
    """Return a baseline of the files that name a product today. Used once, when the guard was introduced."""

    files: dict[str, Any] = {}
    for name in code_files(repository_files(root)):
        if name in GUARD_FILES:
            continue
        try:
            naming = naming_lines((root / name).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        if naming:
            files[name] = {"products": sorted(naming), "naming_lines": len({line for lines in naming.values() for line in lines}),
                           "naming_lines_sha256": lines_digest(naming)}
    return {
        "schema": BASELINE_SCHEMA,
        "guardrail": f"{GUARDRAIL} (planning protocol v1a; plan 2.3 item 9, plan 0 item 3, plan row 8.1 A1)",
        "recorded_on": recorded_on,
        "what_this_is": (
            "The code files that named the AIT or MBRSC product, or their folder in the external data workspace, on the day "
            "the guard was introduced. They are the inspection, registration and gate code of the earlier reference-candidate "
            "work, which the plan keeps unchanged (plan 2.2, AIT invariant: processing_allowed=false). Each is listed with the "
            "SHA-256 of the lines that name a product, so that a new or changed line fails the guard."
        ),
        "what_this_is_not": (
            "Not a grant. A file listed here may not start to process either product. A new file that names a product "
            "fails the guard until a grant is recorded."
        ),
        "grant": (
            "The guardrail says 'a recorded grant receipt' and gives neither its form nor its place (open point A1-OP7). The "
            "guard reads the rights registry (floodguard.rights.REGISTERED_RECORDS): a product is granted when a registered "
            "record of its source is confirmed by the owners and signed by a human."
        ),
        "grant_sources": dict(GRANT_SOURCES),
        "files": dict(sorted(files.items())),
    }
