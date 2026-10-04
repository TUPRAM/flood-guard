"""Run the AIT/MBRSC guard of planning protocol v1a (guardrail GR9) on this checkout.

The guard fails when a committed script names the AIT or MBRSC flood product, or its folder in the external
data workspace, without a recorded grant, and when a file of the diagnosis (plan task A1) puts a figure
beside either name. It reads code and text only: no product file is opened.

Use it before a commit::

    python scripts/check_ait_mbrsc_guard.py

It returns 0 when nothing is refused and 1 otherwise. The same checks run in the test suite
(``tests/test_ait_mbrsc_guard.py``). To make it a Git hook, call it from ``.git/hooks/pre-commit``; the
repository installs no hook by itself.

``--write-baseline`` writes the list of legacy files and refuses to replace an existing one: the baseline was
written once, when the guard was introduced, and a change to it is a decision for the owners.
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
