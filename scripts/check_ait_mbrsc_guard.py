"""Run the AIT/MBRSC guard of planning protocol v1a (guardrail GR9) on this checkout.

The guard fails when a committed script names the AIT or MBRSC flood product, or its folder in the external
data workspace, without a recorded grant; when a legacy file of the baseline gains a line that names one, or
(under ``scripts/`` and ``src/``) a function or class; and when a file of the diagnosis (plan task A1) puts a
figure beside either name. It reads code and text only: no product file is opened.

Use it before a commit::

    python scripts/check_ait_mbrsc_guard.py

It returns 0 when nothing is refused and 1 otherwise. The same checks run in the test suite
(``tests/test_ait_mbrsc_guard.py``), which is how they run in CI. To make it a Git hook, call it from
``.git/hooks/pre-commit``; the repository installs no hook by itself, so on a clone without that hook the
check runs only when the suite or this command is run (open point A1-OP11).

``--write-baseline`` writes the list of legacy files and refuses to replace an existing one: a change to the
baseline is a decision for the owners. The baseline in force is version 2, written late on 4 October 2026
(UTC; 5 October in local time) after the review of plan task A1 widened what the guard reads; version 1, of
earlier that day, is in the Git history.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from floodguard import ait_mbrsc_guard  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    """Run the guard, or write the baseline once."""

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--write-baseline", action="store_true", help="write the list of legacy files; refused when one exists")
    args = parser.parse_args(argv)
    if args.write_baseline:
        path = ROOT / ait_mbrsc_guard.BASELINE_PATH
        if path.exists():
            print(f"{ait_mbrsc_guard.BASELINE_PATH.as_posix()} exists; it is not replaced", file=sys.stderr)
            return 2
        baseline = ait_mbrsc_guard.build_baseline(ROOT, recorded_on=datetime.now(timezone.utc).date().isoformat())
        path.write_bytes((json.dumps(baseline, indent=2, ensure_ascii=True) + "\n").encode("ascii"))
        print(f"wrote {ait_mbrsc_guard.BASELINE_PATH.as_posix()}: {len(baseline['files'])} legacy files")
        return 0
    summary = ait_mbrsc_guard.check(ROOT)
    print(json.dumps(summary, indent=2))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
