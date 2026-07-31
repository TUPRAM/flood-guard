"""Build fresh, deterministic, practice-only SAR remediation cases."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.synthetic_remediation import (  # noqa: E402
    SyntheticRemediationError,
    build_synthetic_remediation_package,
)


def main() -> None:
    """Write a self-hashed remediation source package."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--created-at-utc", required=True)
    args = parser.parse_args()
    try:
        created = datetime.fromisoformat(args.created_at_utc.replace("Z", "+00:00"))
        manifest = build_synthetic_remediation_package(
            args.output_directory,
            created_at_utc=created,
        )
    except (OSError, ValueError, SyntheticRemediationError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    print(f"Wrote conceptual remediation package: {manifest.parent}")
    print("Cases: SYN-REM-001 through SYN-REM-012")
    print(
        "Formal review / calibration / training / evaluation / decision / "
        "FPPS / warning eligibility: false"
    )


if __name__ == "__main__":
    main()
