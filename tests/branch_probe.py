"""Line and branch measurement for a few modules, without coverage.py.

coverage.py is not a dependency of this project, and plan task E2 asks for 100%
branch coverage of ``confidence.py`` and ``normalisation.py``. This helper runs
pytest on the given test files under ``sys.settrace`` and reports, for each
measured module:

* the executable lines that never ran;
* every ``if``, ``elif``, ``for`` and ``while`` statement that went only one
  way: into its body ("true") or past it ("false"). A frame that leaves on an
  exception does not count as "past it".

That is the statement-level meaning of branch coverage that coverage.py uses.
Conditional expressions, ``and`` / ``or`` and comprehension filters are not
separate lines, so neither tool measures them; the report counts them so that a
reader can see how many decisions rest on the tests alone.

To keep the measurement sound the helper refuses a measured module whose branch
statement puts its condition on several lines or its body on the same line.

Run from the repository root::

    python tests/branch_probe.py --module src/floodguard/confidence.py \
        --json-out report.json tests/test_confidence.py

The exit code is 0 when pytest passed; the coverage figures are in the report.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
import types
from pathlib import Path
from typing import Any

EXIT = -1


class ProbeError(ValueError):
    """Raised when a module cannot be measured soundly."""


def _key(path: str) -> str:
    """Return one spelling of a file path, so trace events and arguments compare equal."""

    return os.path.normcase(os.path.realpath(path))


def executable_lines(source: str, filename: str) -> set[int]:
    """Return the lines that hold bytecode, in the module and in every nested code object."""

    lines: set[int] = set()
    stack = [compile(source, filename, "exec")]
    while stack:
        code = stack.pop()
        lines.update(line for _start, _end, line in code.co_lines() if line is not None and line > 0)
        stack.extend(constant for constant in code.co_consts if isinstance(constant, types.CodeType))
    return lines


def branch_statements(source: str) -> list[dict[str, Any]]:
    """Return every if, for and while statement with the line of its condition and of its body.

    Raises:
        ProbeError: for a condition that spans lines or a body on the condition's line.
    """

    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.If, ast.While)):
            head: ast.AST = node.test
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            head = node.iter
        else:
            continue
        body_line = node.body[0].lineno
        if head.lineno != node.lineno or head.end_lineno != node.lineno or body_line == node.lineno:
            raise ProbeError(f"line {node.lineno}: the condition must be on one line and the body on the next")
        found.append({"line": node.lineno, "kind": type(node).__name__.lower(), "body_line": body_line})
    return sorted(found, key=lambda row: row["line"])


def unmeasured_decisions(source: str) -> dict[str, int]:
    """Count the decisions that share a line with their outcomes, which no line tracer can separate."""

    nodes = list(ast.walk(ast.parse(source)))
    return {
        "conditional_expressions": sum(isinstance(node, ast.IfExp) for node in nodes),
        "boolean_operators": sum(isinstance(node, ast.BoolOp) for node in nodes),
        "comprehension_filters": sum(len(node.ifs) for node in nodes if isinstance(node, ast.comprehension)),
    }


class Probe:
    """Record executed lines and line-to-line arcs for the measured files."""

    def __init__(self, targets: set[str]) -> None:
        self.lines: dict[str, set[int]] = {target: set() for target in targets}
        self.arcs: dict[str, set[tuple[int, int]]] = {target: set() for target in targets}
        self._keys: dict[str, str | None] = {}

    def _target(self, filename: str) -> str | None:
        if filename not in self._keys:
            key = _key(filename)
            self._keys[filename] = key if key in self.lines else None
        return self._keys[filename]

    def trace(self, frame: types.FrameType, event: str, _arg: Any) -> Any:
        """The global trace function: follow only frames of the measured files."""

        target = self._target(frame.f_code.co_filename)
        if target is None:
            return None
        lines = self.lines[target]
        arcs = self.arcs[target]
        state: list[Any] = [None, False]  # the last line seen in this frame; an exception is in flight

        def local(inner: types.FrameType, kind: str, _value: Any) -> Any:
            if kind == "line":
                line = inner.f_lineno
                lines.add(line)
                if state[0] is not None:
                    arcs.add((state[0], line))
                state[0] = line
                state[1] = False
            elif kind == "exception":
                state[1] = True
            elif kind == "return" and state[0] is not None and not state[1]:
                arcs.add((state[0], EXIT))
            return local

        return local


def report(path: Path, probe: Probe) -> dict[str, Any]:
    """Compare what ran with what the source holds, for one measured file."""

    source = path.read_text(encoding="utf-8")
    target = _key(str(path))
    executed = probe.lines[target]
    arcs = probe.arcs[target]
    executable = executable_lines(source, str(path))
    statements = branch_statements(source)
    missing_branches = []
    for statement in statements:
        destinations = {end for start, end in arcs if start == statement["line"]}
        if statement["body_line"] not in destinations:
            missing_branches.append({**statement, "missing": "true"})
        if not destinations - {statement["body_line"]}:
            missing_branches.append({**statement, "missing": "false"})
    return {
        "file": path.as_posix(),
        "executable_lines": len(executable),
        "executed_lines": len(executable & executed),
        "missing_lines": sorted(executable - executed),
        "branch_statements": len(statements),
        "branch_outcomes": 2 * len(statements),
        "missing_branches": missing_branches,
        "unmeasured_decisions": unmeasured_decisions(source),
    }


def main(argv: list[str] | None = None) -> int:
    """Run pytest on the test files under the probe and write the report."""

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--module", action="append", required=True, type=Path, help="a source file to measure")
    parser.add_argument("--json-out", required=True, type=Path, help="where the report is written")
    parser.add_argument("--rootdir", type=Path, help="passed to pytest")
    parser.add_argument("tests", nargs="+", help="the pytest files to run")
    args = parser.parse_args(argv)

    import pytest

    modules = [path.resolve() for path in args.module]
    targets = {_key(str(path)) for path in modules}
    loaded = [
        name for name, module in list(sys.modules.items())
        if getattr(module, "__file__", None) and _key(module.__file__) in targets
    ]
    if loaded:
        raise ProbeError(f"already imported before the measurement started: {loaded}")
    for path in modules:
        branch_statements(path.read_text(encoding="utf-8"))

    pytest_args = [*args.tests, "-q", "-p", "no:cacheprovider"]
    if args.rootdir is not None:
        pytest_args.append(f"--rootdir={args.rootdir}")
    probe = Probe(targets)
    sys.settrace(probe.trace)
    try:
        exit_code = int(pytest.main(pytest_args))
    finally:
        sys.settrace(None)

    payload = {
        "pytest_exit_code": exit_code,
        "python": sys.version.split()[0],
        "method": "sys.settrace line arcs; if, elif, for and while statements; exception exits are not outcomes",
        "modules": [report(path, probe) for path in modules],
    }
    args.json_out.write_bytes((json.dumps(payload, indent=2) + "\n").encode("utf-8"))
    return 0 if exit_code == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
