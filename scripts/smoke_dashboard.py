"""Run dependency-light smoke checks against the generated static dashboard."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.dashboard_smoke import (  # noqa: E402
    format_smoke_report,
    run_dashboard_smoke_checks,
    smoke_checks_passed,
)


def main() -> None:
    """Run dashboard smoke checks and exit nonzero on failure."""

    parser = argparse.ArgumentParser(
        description="Smoke-check outputs/dashboard.html through a local static server."
    )
    parser.add_argument(
        "--dashboard",
        type=Path,
        default=REPO_ROOT / "outputs" / "dashboard.html",
        help="Dashboard HTML path. Defaults to outputs/dashboard.html.",
    )
    parser.add_argument(
        "--check-network-tiles",
        action="store_true",
        help=(
            "Probe one OpenStreetMap tile URL. This is useful before demos but "
            "intentionally optional because it depends on live network access."
        ),
    )
    args = parser.parse_args()

    checks = run_dashboard_smoke_checks(
        args.dashboard,
        check_network_tiles=args.check_network_tiles,
    )
    print(format_smoke_report(checks))
    raise SystemExit(0 if smoke_checks_passed(checks) else 1)


if __name__ == "__main__":
    main()
