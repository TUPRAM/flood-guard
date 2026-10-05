"""Guard for the AIT and MBRSC flood products (planning protocol v1a, guardrail ``GR9_ait_mbrsc_guard``).

The guardrail: "A pre-commit test must fail if any committed script reads AIT-VAP001 or MBRSC paths without a
recorded grant receipt. No AIT or MBRSC number appears in committed code or on any public surface." (plan
section 0 item 3, section 2.3 item 9 and row 8.1 A1.) Neither product may be processed until its provider
grants it: the AIT product is a Sentinel Asia value-added product, and the MBRSC map is held blocked by
``docs/mbrsc_reference_mask_clearance_memo.md``.

What this module checks, and how far it reaches:

1. **Paths** (:func:`path_findings`). Every code file of the repository is searched for a name of the two
   products or of their folders (:func:`naming_lines`): a product identifier or file name, the folders of
   the external data workspace that hold them, the bare product word as an identifier or in a short string
   literal, and an import of a legacy module that names a product file or folder. A file that names one
   fails unless (a) it is a **legacy** file, listed in the baseline with the SHA-256 of the lines that name
   the product, so that a new or changed line fails too, or (b) a **grant** for that product is recorded.
   A legacy Python file under ``scripts/`` or ``src/`` is also bound by the set of its functions and
   classes, so that it fails when it gains one.
2. **Numbers** (:func:`number_findings`). In the files of the diagnosis (plan task A1), a figure may not
   stand beside either product name: not in the same line or sentence, not under a JSON key that names a
   product or beside a JSON string that does, and not in a table column whose header names one. The check
   is limited to those files: no automated test can tell which number elsewhere in the repository was
   derived from the two products.

What the guard does **not** see (open points A1-OP8 and A1-OP11): a path that a script reads from a JSON or
CSV manifest; a name that is split across strings or built at run time; new code inside an existing
function of a legacy file; a legacy test or web file that gains code which names no product; any file
that is not a code file. It runs when the test suite runs and as a command; the repository installs no Git
hook. It is a net for the usual case, not a proof.

**What a grant is** is not stated by the signed files: the guardrail says "a recorded grant receipt" and
gives neither its form nor its place (open point A1-OP7). This module reads the one place where the
repository records rights: the registry of :mod:`floodguard.rights`. A product is granted when the registry
holds a record of that source (:data:`GRANT_SOURCES`) that its owners confirmed and a human signed. No such
record exists today, so nothing is granted.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tokenize
from typing import Any

from floodguard import rights

GUARDRAIL = "GR9_ait_mbrsc_guard"
BASELINE_PATH = Path("docs") / "proposal_execution" / "ait_mbrsc_guard_baseline_v2.json"
BASELINE_SCHEMA = "floodguard.ait_mbrsc_guard_baseline.v2"

AIT = "ait"
MBRSC = "mbrsc"
GRANT_SOURCES: Mapping[str, str] = {AIT: "sentinel_asia_ait_vap001", MBRSC: "sentinel_asia_mbrsc"}
"""The kind of source data (``RegisteredRecord.source``) a grant of each product is a record of."""

REFERENCE_FOLDER = (r"[/\\]\s*[\"']?reference_candidates(?![A-Za-z0-9_.])"
                    r"|(?<![A-Za-z0-9_])reference_candidates[\"']?\s*[/\\]")
"""The folder ``reference_candidates`` as a part of a path: it holds nothing but the AIT product, so a path through
it names the product. The same word as a key of a receipt (``receipt["reference_candidates"]``) is not a path."""

SOURCE_PATTERNS: Mapping[str, re.Pattern[str]] = {
    AIT: re.compile(r"ait[-_ ]?vap|vap[-_ ]?001|sentinel_asia_ait|" + REFERENCE_FOLDER, re.IGNORECASE),
    MBRSC: re.compile(r"mbrsc[-_][a-z0-9]|[-_/\\]mbrsc", re.IGNORECASE),
}
"""What names each product on any line of a code file: its product identifier or file name, or its folder in the
external data workspace. The name of this guard (``ait_mbrsc_guard``) is taken out of a line before it is searched."""

SHARED_FOLDER_PATTERN = re.compile(r"sentinel_asia(?!_ait)", re.IGNORECASE)
"""The external folder that holds the MBRSC archive and other Sentinel Asia files; naming it names both products."""

OWN_NAME = re.compile(r"ait[-_/ ]mbrsc[-_ ]guard", re.IGNORECASE)
"""The guard's own name, in a module name, a file name or the words 'AIT/MBRSC guard'. It names no product path."""

WORD_PATTERNS: Mapping[str, re.Pattern[str]] = {
    AIT: re.compile(r"(?<![A-Za-z])ait(?![A-Za-z])", re.IGNORECASE),
    MBRSC: re.compile(r"mbrsc", re.IGNORECASE),
}
"""The bare product words. In a code file they count as a name only in an identifier or in a short string literal
(:func:`code_tokens`): a sentence about the products is not a path."""

SHORT_STRING_CHARS = 80
SHORT_STRING_WORDS = 8
"""A string literal is short, and so can be a label or a path part, below both limits; a longer one is prose."""

PATH_HINT = re.compile(
    r"\.(?:shp|shx|dbf|prj|cpg|sbn|sbx|zip|kmz|kml|gpkg|geojson|tif|tiff)(?![A-Za-z0-9])"
    r"|[/\\]\s*[\"']?sentinel_asia(?![A-Za-z0-9_])|(?<![A-Za-z0-9_])sentinel_asia[\"']?\s*[/\\]"
    r"|" + REFERENCE_FOLDER,
    re.IGNORECASE,
)
"""A naming line that also holds a data file name or the product folder as a path part: the file can open a product."""

CODE_SUFFIXES = frozenset({".py", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".sh", ".ps1", ".bat", ".cmd", ".ipynb", ".r",
                           ".yml", ".yaml", ".toml"})
"""A committed script is any tracked file with one of these suffixes (compared in lower case)."""

GUARD_FILES = frozenset({
    "src/floodguard/ait_mbrsc_guard.py",
    "scripts/check_ait_mbrsc_guard.py",
    "tests/test_ait_mbrsc_guard.py",
})
"""The guard, its command and its test name the products in order to look for them; they read no product file."""

DEFINITION_BOUND_PREFIXES: tuple[str, ...] = ("scripts/", "src/")
"""A legacy Python file under one of these folders is also bound by the set of its functions and classes. Legacy
tests and web files are bound by their naming lines only: other lanes add tests and components to them."""

A1_FILE_PATTERNS: tuple[str, ...] = (
    "scripts/diagnostics/*",
    "outputs/a1_diagnosis/*",
    "outputs/planning_v1/a1_diagnosis_*.json",
    "outputs/planning_v1/run_register/a1_diagnosis_*.json",
    "docs/proposal_execution/automated_track/WHY_THRESHOLD_ONLY_FAILED.md",
    "src/floodguard/abstention_diagnosis.py",
    "src/floodguard/diagnosis_run.py",
    "src/floodguard/diagnosis_layers.py",
    "tests/test_a1_diagnosis_outputs.py",
    "tests/test_abstention_diagnosis.py",
    "tests/test_diagnosis_layers.py",
)
"""The files of plan task A1, in which no figure may stand beside AIT or MBRSC."""

A1_SECTIONS: Mapping[str, str] = {"outputs/planning_v1/README.md": "### Plan task A1: the abstention diagnosis"}
"""Files of which only one section belongs to plan task A1: the text from this heading to the end of the file."""

_MONTH = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?"
          r"|Nov(?:ember)?|Dec(?:ember)?)")
_NOT_A_FIGURE = re.compile(
    r"AIT[-_ ]?VAP[-_ ]?\d+(?:-TH)?|[A-Z]\d{1,2}-OP\d+|EK-\d+|ALOS-2|RADARSAT-2|Sentinel-[12]|GLO-30|SHA-?256|(?:product\s+)?4009"
    r"|(?<![A-Za-z0-9.])[A-Za-z]{1,2}\d{1,2}[a-z]?(?![A-Za-z0-9])(?!\.\d)"
    r"|(?<![A-Za-z])(?:plan|section|item|rule)\s+\d{1,2}(?:\.\d{1,2})?(?![0-9.])"
    r"|(?<![0-9.])\d{1,2}\s*" + _MONTH + r"(?![A-Za-z])",
    re.IGNORECASE,
)
"""Identifiers that hold digits and are not figures: product names, rule and decision numbers (GR9, A1, v1a, D12),
plan sections and items, the product number 4009 and a day with its month. A year, a row number and any other
number are figures here: in the files of the diagnosis a product name stands beside no number at all."""

_NUMBER_KEY_WORD = re.compile(r"(?<![a-z])ait(?![a-z])|mbrsc")
_SENTENCE_END = re.compile(r"(?<=[.!?:;])\s+")


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


# ---------------------------------------------------------------------------
# Names of a product in a code file
# ---------------------------------------------------------------------------


def _is_short(text: str) -> bool:
    return len(text) <= SHORT_STRING_CHARS and "\n" not in text and len(text.split()) < SHORT_STRING_WORDS


def _python_tokens(text: str) -> Iterator[tuple[int, str, str]]:
    """Yield the identifiers and the string literals of Python source, adjacent literals joined as Python joins them."""

    pending: list[str] = []
    pending_line = 0
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        kind = tokenize.tok_name[token.type]
        if kind in ("STRING", "FSTRING_START", "FSTRING_MIDDLE", "FSTRING_END"):
            if not pending:
                pending_line = token.start[0]
            pending.append(token.string)
            continue
        if pending and kind in ("NL", "COMMENT"):
            continue
        if pending:
            yield pending_line, "string", " ".join(pending)
            pending = []
        if kind == "NAME":
            yield token.start[0], "identifier", token.string
    if pending:
        yield pending_line, "string", " ".join(pending)


def _fstring_identifiers(text: str) -> Iterator[tuple[int, str, str]]:
    """Yield the names used inside the expressions of f-strings.

    Before Python 3.12 the tokenizer returns an f-string as one string, so a name used only inside one
    (``f"{(flooded & ait).sum()}"``) is found through the syntax tree.
    """

    try:
        tree = ast.parse(text)
    except SyntaxError:
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            for inner in ast.walk(node):
                if isinstance(inner, ast.Name):
                    yield inner.lineno, "identifier", inner.id
                elif isinstance(inner, ast.Attribute):
                    yield inner.lineno, "identifier", inner.attr


_QUOTED = re.compile(r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'|`(?:[^`\\\n]|\\.)*`')
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_LINE_COMMENT = re.compile(r"(?:^|\s)(?://|#).*$")


def _generic_tokens(text: str) -> Iterator[tuple[int, str, str]]:
    """Yield the identifiers and the quoted strings of source in another language, line by line.

    A line that starts a comment (``//``, ``#``, ``*`` or ``/*``) is skipped, and so is the rest of a line
    after ``//`` or ``#``. It is a rough reading: it knows no grammar.
    """

    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith(("//", "#", "*", "/*", "REM ", "rem ", "::")):
            continue
        for match in _QUOTED.finditer(line):
            yield number, "string", match.group(0)
        rest = _LINE_COMMENT.sub(" ", _QUOTED.sub(" ", line))
        for match in _IDENTIFIER.finditer(rest):
            yield number, "identifier", match.group(0)


def notebook_source(text: str) -> str:
    """Return the source of the code cells of a notebook, one cell after another; outputs are left out.

    A file that is not a notebook is returned as it is.
    """

    try:
        document = json.loads(text)
    except ValueError:
        return text
    if not isinstance(document, dict) or not isinstance(document.get("cells"), list):
        return text
    cells: list[str] = []
    for cell in document["cells"]:
        if isinstance(cell, dict) and cell.get("cell_type", "code") == "code":
            source = cell.get("source", "")
            cells.append("".join(source) if isinstance(source, list) else str(source))
    return "\n".join(cells)


def code_tokens(text: str, suffix: str) -> list[tuple[int, str, str]]:
    """Return the identifiers and the string literals of a code file as ``(line, kind, text)``.

    Python is read with its own tokenizer; a file the tokenizer refuses, and every other language, is read
    line by line.
    """

    if suffix.lower() in (".py", ".ipynb"):
        try:
            return list(_python_tokens(text)) + list(_fstring_identifiers(text))
        except (tokenize.TokenError, IndentationError, SyntaxError):
            pass
    return list(_generic_tokens(text))


def _identifier_parts(identifier: str) -> list[str]:
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", identifier)
    return [part.lower() for part in re.split(r"[_\W]+", spaced) if part]


def word_lines(text: str, suffix: str) -> dict[str, set[int]]:
    """Return, for each product, the lines on which its bare word is an identifier or stands in a short string literal."""

    found: dict[str, set[int]] = {AIT: set(), MBRSC: set()}
    for line, kind, token in code_tokens(text, suffix):
        token = OWN_NAME.sub(" ", token)
        if kind == "identifier":
            parts = _identifier_parts(token)
            if AIT in parts:
                found[AIT].add(line)
            if any(MBRSC in part for part in parts):
                found[MBRSC].add(line)
        elif _is_short(token):
            for product, pattern in WORD_PATTERNS.items():
                if pattern.search(token):
                    found[product].add(line)
    return found


def import_lines(text: str, reader_modules: Mapping[str, Sequence[str]]) -> dict[int, set[str]]:
    """Return the lines of Python source that import a legacy reader module, each with the products that module names.

    Source that does not parse is read line by line for ``import`` and ``from`` statements.
    """

    found: dict[int, set[str]] = {}
    if not reader_modules:
        return found

    def products_of(candidate: str) -> set[str]:
        return {product for module, products in reader_modules.items()
                if candidate == module or candidate.startswith(module + ".") for product in products}

    try:
        tree = ast.parse(text)
    except SyntaxError:
        for number, line in enumerate(text.splitlines(), start=1):
            if re.match(r"\s*(?:from|import)\s", line):
                for module, products in reader_modules.items():
                    if re.search(r"(?<![A-Za-z0-9_])" + re.escape(module.rsplit(".", 1)[-1]) + r"(?![A-Za-z0-9_])", line):
                        found.setdefault(number, set()).update(products)
        return found
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if products_of(alias.name):
                    found.setdefault(alias.lineno, set()).update(products_of(alias.name))
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            base = node.module or ""
            for alias in node.names:
                named = products_of(base) | products_of(f"{base}.{alias.name}")
                if named:
                    found.setdefault(alias.lineno, set()).update(named)
    return found


def naming_lines(text: str, suffix: str = ".py", reader_modules: Mapping[str, Sequence[str]] | None = None) -> dict[str, list[str]]:
    """Return, for each product, the lines of a code file that name it or its folder, stripped of outer white space.

    Args:
        text: The source of the file.
        suffix: Its suffix, which decides how identifiers and string literals are found.
        reader_modules: The legacy modules that name a product file or folder, each with the products it
            names; an import of one names those products.
    """

    if suffix.lower() == ".ipynb":
        text = notebook_source(text)
    lines = text.splitlines()
    words = word_lines(text, suffix)
    imports = import_lines(text, reader_modules or {}) if suffix.lower() in (".py", ".ipynb") else {}
    found: dict[str, list[str]] = {AIT: [], MBRSC: []}
    for number, line in enumerate(lines, start=1):
        searched = OWN_NAME.sub(" ", line)
        shared = SHARED_FOLDER_PATTERN.search(searched) is not None
        for product, pattern in SOURCE_PATTERNS.items():
            if shared or pattern.search(searched) or number in words[product] or product in imports.get(number, ()):
                found[product].append(line.strip())
    return {product: named for product, named in found.items() if named}


def lines_digest(lines_by_product: Mapping[str, Sequence[str]]) -> str:
    """Return the SHA-256 of the naming lines of a file, so that a new or changed line is noticed."""

    lines = sorted({line for lines in lines_by_product.values() for line in lines})
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def definitions(text: str) -> list[str] | None:
    """Return the functions and classes of Python source by their qualified names, or None when it does not parse."""

    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    names: list[str] = []

    def walk(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.append(prefix + child.name)
                walk(child, prefix + child.name + ".")
            else:
                walk(child, prefix)

    walk(tree, "")
    return sorted(names)


def definitions_digest(names: Sequence[str]) -> str:
    """Return the SHA-256 of a set of function and class names."""

    return hashlib.sha256("\n".join(sorted(names)).encode("utf-8")).hexdigest()


def is_definition_bound(name: str) -> bool:
    """Say whether a legacy file is also bound by the set of its functions and classes."""

    return name.endswith(".py") and name.startswith(DEFINITION_BOUND_PREFIXES)


def module_name(path: str) -> str | None:
    """Return the dotted name of a module under ``src/``, or None for any other file."""

    if not path.startswith("src/") or not path.endswith(".py"):
        return None
    return path[len("src/"):-len(".py")].replace("/", ".")


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


def read_baseline(root: Path) -> dict[str, Any]:
    """Read the baseline document.

    Raises:
        GuardError: when the baseline is missing or is not in the schema this module reads.
    """

    path = root / BASELINE_PATH
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise GuardError(f"the baseline of the guard is missing: {BASELINE_PATH.as_posix()}") from error
    files = document.get("files")
    if document.get("schema") != BASELINE_SCHEMA or not isinstance(files, dict) or not isinstance(document.get("reader_modules", {}), dict):
        raise GuardError("the baseline of the guard is not in the schema this module reads")
    for name, entry in files.items():
        if not isinstance(entry, dict) or not re.fullmatch(r"[0-9a-f]{64}", str(entry.get("naming_lines_sha256", ""))) \
                or not set(entry.get("products", [])) <= set(GRANT_SOURCES) or not entry.get("products"):
            raise GuardError(f"the baseline entry of {name} needs the SHA-256 of its naming lines and its products")
        bound = entry.get("definitions_sha256")
        if bound is not None and not re.fullmatch(r"[0-9a-f]{64}", str(bound)):
            raise GuardError(f"the baseline entry of {name} has a malformed SHA-256 of its definitions")
    return document


def load_baseline(root: Path) -> dict[str, dict[str, Any]]:
    """Read the legacy files of the baseline: path to the SHA-256 of its naming lines and the products it names.

    Raises:
        GuardError: when the baseline is missing or is not in the schema this module reads.
    """

    return read_baseline(root)["files"]


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


def path_findings(root: Path, files: Iterable[str], baseline: Mapping[str, Mapping[str, Any]], grants: Mapping[str, str],
                  reader_modules: Mapping[str, Sequence[str]] | None = None) -> list[Finding]:
    """Return every committed script that names a product it may not read.

    A file passes when it names no product, when it is one of the guard's own files, when it is a legacy file
    whose naming lines (and, for a Python file under ``scripts/`` or ``src/``, whose functions and classes)
    are those of the baseline, or when every product it names is granted.
    """

    findings: list[Finding] = []
    for name in code_files(files):
        if name in GUARD_FILES:
            continue
        try:
            text = (root / name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        naming = naming_lines(text, Path(name).suffix, reader_modules)
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
        elif entry.get("definitions_sha256") is not None:
            names = definitions(text)
            if names is None or definitions_digest(names) != entry["definitions_sha256"]:
                findings.append(Finding(name, "legacy_file_gained_or_lost_a_definition", missing,
                                        "the functions and classes of the file are not those the baseline records"))
    return findings


# ---------------------------------------------------------------------------
# Figures beside a product name, in the files of the diagnosis
# ---------------------------------------------------------------------------


def _matches(name: str, patterns: Sequence[str]) -> bool:
    return any(Path(name).match(pattern) for pattern in patterns)


def names_a_product(text: str) -> tuple[str, ...]:
    """Return the products a piece of text names by their bare word, in any case; the guard's own name does not count."""

    searched = OWN_NAME.sub(" ", text)
    return tuple(product for product, pattern in WORD_PATTERNS.items() if pattern.search(searched))


def holds_a_figure(text: str) -> bool:
    """Say whether a piece of text holds a digit that is not part of an identifier or of a day with its month."""

    return re.search(r"\d", _NOT_A_FIGURE.sub(" ", OWN_NAME.sub(" ", text))) is not None


def figure_in_line(line: str) -> bool:
    """Say whether a line that names AIT or MBRSC also holds a figure.

    Product identifiers, rule and section numbers and a day with its month are not figures. Any other digit
    is, a year included.
    """

    return bool(names_a_product(line)) and holds_a_figure(line)


def _key_names_a_product(key: str) -> bool:
    return _NUMBER_KEY_WORD.search(OWN_NAME.sub(" ", str(key)).lower()) is not None


def _numbers_beneath(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        return holds_a_figure(value)
    if isinstance(value, dict):
        return any(_numbers_beneath(child) for child in value.values())
    if isinstance(value, list):
        return any(_numbers_beneath(child) for child in value)
    return False


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_label(value: Any) -> bool:
    return isinstance(value, str) and _is_short(value) and bool(names_a_product(value))


def json_findings(document: Any, path: str = "$") -> list[str]:
    """Return the places of a JSON document where a number stands under or beside a product name.

    A number, or a string that holds a figure, anywhere under a key that names a product is refused. So is a
    number that is a sibling of a short string naming a product (a label, not a sentence), in an object or in
    a list, and a string in which a figure stands in the sentence that names a product.
    """

    found: list[str] = []
    if isinstance(document, str):
        if any(figure_in_line(sentence) for sentence in _SENTENCE_END.split(" ".join(document.split()))):
            found.append(f"{path}: a figure in the sentence that names a product")
    elif isinstance(document, dict):
        naming_strings = [key for key, value in document.items() if _is_label(value)]
        for key, value in document.items():
            here = f"{path}.{key}"
            if _key_names_a_product(key) and _numbers_beneath(value):
                found.append(f"{here}: a number under a key that names a product")
            elif naming_strings and _is_number(value):
                found.append(f"{here}: a number beside the string at {path}.{naming_strings[0]}, which names a product")
            found += json_findings(value, here)
    elif isinstance(document, list):
        names = any(_is_label(item) for item in document)
        for index, item in enumerate(document):
            if names and _is_number(item):
                found.append(f"{path}[{index}]: a number beside a string that names a product")
            found += json_findings(item, f"{path}[{index}]")
    return found


def _table_cells(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith("|"):
        return None
    return [cell.strip() for cell in stripped.strip("|").split("|")]


def text_findings(text: str, *, lines_only: bool = False) -> list[tuple[int, str]]:
    """Return the lines of a text where a figure stands beside a product name.

    Three readings: the line itself; the sentence, across the lines of a wrapped paragraph; and a table
    column whose header names a product. With ``lines_only`` the first reading alone is made (for the raw
    text of a JSON file, whose values :func:`json_findings` reads).
    """

    lines = text.splitlines()
    found: dict[int, str] = {}
    for number, line in enumerate(lines, start=1):
        if figure_in_line(line):
            found[number] = line.strip()
    start = len(lines) if lines_only else 0
    while start < len(lines):
        if not lines[start].strip():
            start += 1
            continue
        end = start
        while end < len(lines) and lines[end].strip():
            end += 1
        block = lines[start:end]
        rows = [_table_cells(line) for line in block]
        if all(row is not None for row in rows):
            header = rows[0] or []
            for column, cell in enumerate(header):
                if not names_a_product(cell):
                    continue
                for offset, row in enumerate(rows[1:], start=1):
                    if row is not None and column < len(row) and holds_a_figure(row[column]):
                        found.setdefault(start + offset + 1, lines[start + offset].strip())
        elif not any(number in found for number in range(start + 1, end + 1)):
            # A sentence wrapped over several lines: no single line of it holds both the name and the figure.
            paragraph = " ".join(line.strip() for line in block)
            for sentence in _SENTENCE_END.split(paragraph):
                if figure_in_line(sentence):
                    found.setdefault(start + 1, sentence.strip())
        start = end
    return sorted(found.items())


def number_findings(root: Path, files: Iterable[str], patterns: Sequence[str] = A1_FILE_PATTERNS,
                    sections: Mapping[str, str] = A1_SECTIONS) -> list[Finding]:
    """Return every place of the diagnosis files where a figure stands beside AIT or MBRSC."""

    findings: list[Finding] = []
    for name in sorted(files):
        if name in GUARD_FILES or not (_matches(name, patterns) or name in sections):
            continue
        try:
            text = (root / name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        offset = 0
        if name in sections:
            head, found, tail = text.partition(sections[name])
            if not found:
                continue
            offset = head.count("\n")
            text = found + tail
        for number, line in text_findings(text, lines_only=name.endswith(".json")):
            findings.append(Finding(name, "figure_beside_a_product_name", names_a_product(line), f"line {number + offset}: {line[:160]}"))
        if name.endswith(".json"):
            try:
                document = json.loads(text)
            except ValueError:
                continue
            for place in json_findings(document):
                findings.append(Finding(name, "figure_beside_a_product_name", (AIT, MBRSC), place[:200]))
    return findings


def reader_modules_of(document: Mapping[str, Any]) -> dict[str, list[str]]:
    """Return the legacy modules of a baseline that name a product file or folder, each with its products."""

    return {str(module): list(products) for module, products in document.get("reader_modules", {}).items()}


def check(root: Path, *, registry: rights.RightsRegistry | None = None) -> dict[str, Any]:
    """Run both checks on a checkout and return what was looked at and what was refused."""

    files = repository_files(root)
    document = read_baseline(root)
    baseline = document["files"]
    grants = recorded_grants(registry or rights.RightsRegistry(root))
    findings = path_findings(root, files, baseline, grants, reader_modules_of(document)) + number_findings(root, files)
    return {
        "guardrail": GUARDRAIL,
        "code_files_searched": len(code_files(files)),
        "legacy_files_in_the_baseline": len(baseline),
        "legacy_files_bound_by_their_definitions": sum(entry.get("definitions_sha256") is not None for entry in baseline.values()),
        "legacy_reader_modules": sorted(reader_modules_of(document)),
        "grants_recorded": dict(grants),
        "findings": [finding.describe() for finding in findings],
        "passed": not findings,
    }


def build_baseline(root: Path, *, recorded_on: str) -> dict[str, Any]:
    """Return a baseline of the files that name a product today.

    Two passes: the first finds the legacy modules that name a product file or folder; the second counts an
    import of one of them as a name of its products, so that the files which import them are listed too.
    """

    def scan(reader_modules: Mapping[str, Sequence[str]]) -> dict[str, tuple[str, dict[str, list[str]]]]:
        named: dict[str, tuple[str, dict[str, list[str]]]] = {}
        for name in code_files(repository_files(root)):
            if name in GUARD_FILES:
                continue
            try:
                text = (root / name).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            naming = naming_lines(text, Path(name).suffix, reader_modules)
            if naming:
                named[name] = (text, naming)
        return named

    readers: dict[str, list[str]] = {}
    for name, (_text, naming) in scan({}).items():
        module = module_name(name)
        if module is not None and any(PATH_HINT.search(OWN_NAME.sub(" ", line)) for lines in naming.values() for line in lines):
            readers[module] = sorted(naming)
    files: dict[str, Any] = {}
    for name, (text, naming) in scan(readers).items():
        entry: dict[str, Any] = {"products": sorted(naming), "naming_lines": len({line for lines in naming.values() for line in lines}),
                                 "naming_lines_sha256": lines_digest(naming)}
        names = definitions(text) if is_definition_bound(name) else None
        if names is not None:
            entry["definitions"] = len(names)
            entry["definitions_sha256"] = definitions_digest(names)
        files[name] = entry
    return {
        "schema": BASELINE_SCHEMA,
        "guardrail": f"{GUARDRAIL} (planning protocol v1a; plan 2.3 item 9, plan 0 item 3, plan row 8.1 A1)",
        "recorded_on": recorded_on,
        "replaces": "docs/proposal_execution/ait_mbrsc_guard_baseline_v1.json (4 October 2026), after the review of plan task A1: "
                    "the guard now also reads the bare product words in identifiers and short strings, the folder "
                    "reference_candidates alone and imports of the legacy reader modules, so more files name a product.",
        "what_this_is": (
            "The code files that named the AIT or MBRSC product, or their folders in the external data workspace, on the day "
            "this baseline was written. They are the inspection, registration and gate code of the earlier reference-candidate "
            "work, which the plan keeps unchanged (plan 2.2, AIT invariant: processing_allowed=false), with the tests and the "
            "web files that name the blocked records. Each is listed with the SHA-256 of the lines that name a product, so "
            "that a new or changed line fails the guard. A Python file under scripts/ or src/ is also listed with the SHA-256 "
            "of the names of its functions and classes, so that it fails when it gains or loses one."
        ),
        "what_this_is_not": (
            "Not a grant, and not a proof that a listed file processes neither product. The guard notices a new or changed "
            "naming line, and a new function or class in a legacy file under scripts/ or src/. It does not notice new code "
            "inside an existing function, or new code in a legacy test or web file that names no product. A new file that "
            "names a product fails the guard until a grant is recorded."
        ),
        "grant": (
            "The guardrail says 'a recorded grant receipt' and gives neither its form nor its place (open point A1-OP7). The "
            "guard reads the rights registry (floodguard.rights.REGISTERED_RECORDS): a product is granted when a registered "
            "record of its source is confirmed by the owners and signed by a human."
        ),
        "grant_sources": dict(GRANT_SOURCES),
        "reader_modules": dict(sorted(readers.items())),
        "reader_modules_note": "Legacy modules whose naming lines hold a data file name or the product folder as a path part. "
                               "An import of one of them names its products.",
        "files": dict(sorted(files.items())),
    }
