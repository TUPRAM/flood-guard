"""Wording lint for reader-facing FloodGuard text.

FloodGuard is a preparedness and post-event prioritisation tool. Its text must
not claim real-time detection, a forecast, an official warning, a validation,
return periods or a road schedule. The rules are data: a JSON file with banned
patterns, an allowlist of explicit negations ("not a forecast") and seeded
examples. The Mae Sai replay's rules are
``apps/web/src/lib/replay-wording-rules.json``; the web tests read the same file
through ``replay-wording-lint.ts``, so both sides apply the same patterns.

How a text is judged:

1. :func:`normalise` removes web addresses, collapses white space and makes
   curly apostrophes and non-breaking hyphens plain.
2. Every allowlisted negation is removed, in order.
3. Whatever still matches a banned pattern is a finding.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

_URL = re.compile(r"https?://[^\s\"'<>)\]]+")
_WHITE_SPACE = re.compile(r"\s+")
_REMOVED = " ∅ "
"""Marker left where a negation was removed, so the two halves of a sentence cannot join into a new match."""

NON_TEXT_KEYS: frozenset[str] = frozenset({"href", "url", "urls", "source_url", "sha256", "scene", "source_file"})
"""JSON keys whose values are addresses, hashes or file names rather than copy."""


class WordingRulesError(ValueError):
    """Raised when a wording rules file is malformed."""


@dataclass(frozen=True)
class WordingRule:
    """One banned pattern with the reason and seeded examples that must be flagged."""

    id: str
    pattern: re.Pattern[str]
    message: str
    bad: tuple[str, ...]


@dataclass(frozen=True)
class WordingAllowance:
    """One allowlisted negation with examples that must pass."""

    id: str
    pattern: re.Pattern[str]
    why: str
    ok: tuple[str, ...]


@dataclass(frozen=True)
class WordingRules:
    """Compiled wording rules: allowances are applied first, in order, then the banned rules."""

    allow: tuple[WordingAllowance, ...]
    rules: tuple[WordingRule, ...]
    mixed: tuple[tuple[str, tuple[str, ...]], ...]

    @property
    def rule_ids(self) -> tuple[str, ...]:
        return tuple(rule.id for rule in self.rules)


@dataclass(frozen=True)
class WordingFinding:
    """One banned pattern found in a text."""

    rule: str
    match: str
    context: str
    source: str
    message: str

    def describe(self) -> str:
        return f'[{self.rule}] {self.source}: "...{self.context}..." - {self.message}'


def load_rules(path: Path | str) -> WordingRules:
    """Read and compile a wording rules file.

    Raises :class:`WordingRulesError` when the file lacks rules, an id repeats, a
    pattern does not compile or a rule has no seeded example.
    """
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict) or not isinstance(document.get("rules"), list) or not document["rules"]:
        raise WordingRulesError("a wording rules file needs a non-empty rules list")
    rules = tuple(WordingRule(_text(item, "id"), _compile(item), _text(item, "message"), _examples(item, "bad"))
                  for item in document["rules"])
    allow = tuple(WordingAllowance(_text(item, "id"), _compile(item), _text(item, "why"), _examples(item, "ok"))
                  for item in document.get("allow", []))
    ids = [item.id for item in (*rules, *allow)]
    if len(set(ids)) != len(ids):
        raise WordingRulesError("wording rule and allowance ids must be unique")
    mixed = tuple((str(item["text"]), tuple(item["rules"])) for item in document.get("mixed", []))
    return WordingRules(allow=allow, rules=rules, mixed=mixed)


def normalise(text: str) -> str:
    """Return ``text`` as the linter reads it (the same steps as ``normaliseWording`` on the web side)."""
    text = _URL.sub(" ", text)
    text = text.replace("‘", "'").replace("’", "'").replace("‐", "-").replace("‑", "-")
    return _WHITE_SPACE.sub(" ", text).strip()


def find_violations(text: str, rules: WordingRules, source: str = "") -> list[WordingFinding]:
    """Return every banned pattern still in ``text`` once the allowlisted negations are removed."""
    remaining = normalise(text)
    for allowance in rules.allow:
        remaining = allowance.pattern.sub(_REMOVED, remaining)
    findings = []
    for rule in rules.rules:
        for match in rule.pattern.finditer(remaining):
            context = remaining[max(0, match.start() - 40):match.end() + 40]
            findings.append(WordingFinding(rule.id, match.group(0), context, source, rule.message))
    return findings


def lint_texts(items: Iterable[tuple[str, str]], rules: WordingRules) -> list[WordingFinding]:
    """Lint ``(source, text)`` pairs and return all findings."""
    return [finding for source, text in items for finding in find_violations(text, rules, source)]


def json_strings(value: Any, path: str = "$", skip_keys: frozenset[str] = NON_TEXT_KEYS) -> Iterator[tuple[str, str]]:
    """Yield ``(path, text)`` for every string value of a JSON document (keys are names, not copy)."""
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from json_strings(item, f"{path}[{index}]", skip_keys)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key not in skip_keys:
                yield from json_strings(item, f"{path}.{key}", skip_keys)


def python_strings(source: str) -> list[str]:
    """Return the string constants of Python ``source`` that can reach a reader.

    Docstrings are documentation for developers and are left out. An f-string
    contributes its literal parts joined by ``{...}``.
    """
    tree = ast.parse(source)
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                docstrings.add(id(first.value))
    strings: list[str] = []
    joined_parts: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            parts = [part.value if isinstance(part, ast.Constant) and isinstance(part.value, str) else " {...} " for part in node.values]
            joined_parts.update(id(part) for part in node.values)
            strings.append("".join(parts))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings and id(node) not in joined_parts:
            strings.append(node.value)
    return strings


def markdown_section(text: str, heading: str) -> str:
    """Return the section of a Markdown document that starts at ``heading`` and runs to the next heading of that level or higher."""
    lines = text.splitlines()
    try:
        start = next(index for index, line in enumerate(lines) if line.strip() == heading)
    except StopIteration as exc:
        raise WordingRulesError(f"heading not found: {heading}") from exc
    level = len(heading) - len(heading.lstrip("#"))
    end = len(lines)
    for index in range(start + 1, len(lines)):
        match = re.match(r"(#+) ", lines[index])
        if match and len(match.group(1)) <= level:
            end = index
            break
    return "\n".join(lines[start:end])


def _text(item: Any, key: str) -> str:
    value = item.get(key) if isinstance(item, dict) else None
    if not isinstance(value, str) or not value.strip():
        raise WordingRulesError(f"every wording rule needs a non-empty {key}")
    return value


def _examples(item: dict, key: str) -> tuple[str, ...]:
    values = item.get(key)
    if not isinstance(values, list) or not values or not all(isinstance(value, str) and value.strip() for value in values):
        raise WordingRulesError(f"{item.get('id')}: {key} must list at least one example")
    return tuple(values)


def _compile(item: dict) -> re.Pattern[str]:
    pattern = _text(item, "pattern")
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        raise WordingRulesError(f"{item.get('id')}: pattern does not compile: {exc}") from exc
