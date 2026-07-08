"""Build the Mae Sai public reference-candidate decision note."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.reference_decision import write_mae_sai_reference_decision  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inspection",
        type=Path,
        default=REPO_ROOT / "outputs" / "public_reference_file_inspection_manifest.csv",
    )
    parser.add_argument(
        "--cems",
        type=Path,
        default=REPO_ROOT / "outputs" / "cems_product_candidate_manifest.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "outputs" / "mae_sai_reference_candidate_decision.md",
    )
    args = parser.parse_args(argv)
    written = write_mae_sai_reference_decision(args.inspection, args.cems, args.output)
    print(f"Wrote {written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
