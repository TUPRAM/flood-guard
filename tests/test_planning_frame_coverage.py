"""Plan task E2: 100% line and branch coverage of ``confidence.py`` and ``normalisation.py``.

coverage.py is not a dependency of this project, so the figure is measured by
``tests/branch_probe.py``: it runs the two test files under ``sys.settrace`` in
a child process and reports every executable line that did not run and every
``if``, ``elif``, ``for`` and ``while`` statement that went only one way.

The first test is the measurement. The others check the probe itself on an
invented module, so that a green measurement means what it says: it reports a
line that never ran, a branch taken one way only, a loop never entered, and it
does not count a frame that leaves on an exception as the other way.

The two modules hold no conditional expression. Their ``and`` / ``or`` conditions
and comprehension filters share a line with their outcomes, so no line tracer
separates them; ``tests/test_confidence.py`` and ``tests/test_normalisation.py``
exercise each operand on its own.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tests" / "branch_probe.py"
MEASURED = ("src/floodguard/confidence.py", "src/floodguard/normalisation.py")
TEST_FILES = ("tests/test_confidence.py", "tests/test_normalisation.py")

_SPEC = importlib.util.spec_from_file_location("branch_probe", PROBE)
assert _SPEC is not None and _SPEC.loader is not None
branch_probe = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(branch_probe)

SAMPLE_MODULE = '''\
def classify(value):
    if value > 10:
        return "high"
    if value < 0:
        raise ValueError("negative")
    for item in range(value):
        if item == 99:
            return "never"
    return "low"


def strict(value):
    if value.flag:
        return 1
    return 0


def unused():
    return 1
'''

SAMPLE_TEST = '''\
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import sample_module  # noqa: E402


def test_partly():
    assert sample_module.classify(0) == "low"
    with pytest.raises(ValueError):
        sample_module.classify(-1)
    with pytest.raises(AttributeError):
        sample_module.strict(None)


def test_more():
    if not {more}:
        return
    assert sample_module.classify(11) == "high"
    assert sample_module.classify(3) == "low"
    assert sample_module.unused() == 1
'''


def _measure(cwd: Path, modules: tuple[str, ...], tests: tuple[str, ...], out: Path, *extra: str) -> dict[str, Any]:
    arguments = [sys.executable, str(PROBE)]
    for module in modules:
        arguments += ["--module", module]
    arguments += ["--json-out", str(out), *extra, *tests]
    completed = subprocess.run(arguments, cwd=cwd, capture_output=True, text=True, timeout=900)
    assert completed.returncode == 0, completed.stdout[-3000:] + completed.stderr[-3000:]
    return json.loads(out.read_text(encoding="utf-8"))


def test_confidence_and_normalisation_have_full_line_and_branch_coverage(tmp_path: Path) -> None:
    report = _measure(ROOT, MEASURED, TEST_FILES, tmp_path / "report.json")
    assert report["pytest_exit_code"] == 0
    assert [Path(module["file"]).name for module in report["modules"]] == ["confidence.py", "normalisation.py"]
    for module in report["modules"]:
        name = Path(module["file"]).name
        assert module["missing_lines"] == [], f"{name}: lines that never ran"
        assert module["missing_branches"] == [], f"{name}: branches taken one way only"
        assert module["executed_lines"] == module["executable_lines"] > 300
        assert module["branch_statements"] >= 50 and module["branch_outcomes"] == 2 * module["branch_statements"]
        # No conditional expression hides a two-way choice from the line tracer.
        assert module["unmeasured_decisions"]["conditional_expressions"] == 0


def _sample(tmp_path: Path, *, more: bool) -> dict[str, Any]:
    (tmp_path / "sample_module.py").write_text(SAMPLE_MODULE, encoding="utf-8")
    (tmp_path / "test_sample.py").write_text(SAMPLE_TEST.format(more=more), encoding="utf-8")
    report = _measure(
        tmp_path, ("sample_module.py",), ("test_sample.py",), tmp_path / "report.json", "--rootdir", str(tmp_path)
    )
    assert report["pytest_exit_code"] == 0
    return report["modules"][0]


def test_probe_reports_lines_and_branches_that_did_not_run(tmp_path: Path) -> None:
    module = _sample(tmp_path, more=False)
    missing = {(row["line"], row["missing"]) for row in module["missing_branches"]}
    assert missing == {
        (2, "true"),                 # value > 10 never held
        (6, "true"),                 # the loop was never entered
        (7, "true"), (7, "false"),   # the statement inside the loop never ran
        (13, "true"), (13, "false"),  # the frame left on an exception: neither way counts
    }
    assert module["missing_lines"] == [3, 7, 8, 14, 15, 19]
    assert module["branch_statements"] == 5 and module["branch_outcomes"] == 10
    assert module["executed_lines"] == module["executable_lines"] - 6


def test_probe_reports_only_what_is_still_missing_after_more_tests(tmp_path: Path) -> None:
    module = _sample(tmp_path, more=True)
    missing = {(row["line"], row["missing"]) for row in module["missing_branches"]}
    # item == 99 cannot hold for a value of at most 10, and strict() still only raises.
    assert missing == {(7, "true"), (13, "true"), (13, "false")}
    assert module["missing_lines"] == [8, 14, 15]


def test_probe_refuses_layouts_it_cannot_measure_and_counts_what_it_does_not() -> None:
    with pytest.raises(branch_probe.ProbeError, match="line 2"):
        branch_probe.branch_statements("def f(x):\n    if x: return 1\n    return 0\n")
    with pytest.raises(branch_probe.ProbeError, match="line 2"):
        branch_probe.branch_statements("def f(x, y):\n    if (x and\n            y):\n        return 1\n    return 0\n")
    source = "def f(x, y):\n    z = 1 if x else 2\n    return [i for i in y if i and z]\n"
    assert branch_probe.branch_statements(source) == []
    assert branch_probe.unmeasured_decisions(source) == {
        "conditional_expressions": 1, "boolean_operators": 1, "comprehension_filters": 1,
    }
    assert branch_probe.executable_lines(source, "sample.py") == {1, 2, 3}
    statements = branch_probe.branch_statements("def f(x):\n    while x:\n        x -= 1\n    for i in x:\n        pass\n")
    assert [(row["line"], row["kind"], row["body_line"]) for row in statements] == [(2, "while", 3), (4, "for", 5)]
