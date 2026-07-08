"""Resolve CEMS EMSR754/EMSR756 public AOI/product metadata without downloads."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.cems import write_cems_product_manifest  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    """Run the CEMS product resolver."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--activation-code",
        action="append",
        default=None,
        help="Activation code to resolve. Repeat to pass multiple codes.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "outputs" / "cems_product_candidate_manifest.csv",
    )
    parser.add_argument("--retrieved-at", default=None)
    args = parser.parse_args(argv)

    codes = tuple(args.activation_code or ["EMSR754", "EMSR756"])
    written = write_cems_product_manifest(
        args.output,
        activation_codes=codes,
        retrieved_at_utc=args.retrieved_at,
    )
    print(f"Wrote {written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
