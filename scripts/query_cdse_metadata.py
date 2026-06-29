"""Query CDSE Products metadata without downloading product assets."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.cdse import (  # noqa: E402
    CDSE_OUTPUT_COLUMNS,
    CDSE_PROFILES,
    build_cdse_products_url,
    fetch_cdse_products,
    get_cdse_profile,
    parse_cdse_products,
)


def main(argv: list[str] | None = None) -> int:
    """Run the no-download CDSE metadata query CLI."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        required=True,
        choices=sorted(CDSE_PROFILES),
        help="Named CDSE query profile.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=None,
        help="Override OData $top row limit.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional CSV output path for parsed metadata rows.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the OData URL only; do not call the network.",
    )
    args = parser.parse_args(argv)

    profile = get_cdse_profile(args.profile, top=args.top)
    url = build_cdse_products_url(profile)
    if args.dry_run:
        print(url)
        return 0

    response_json = fetch_cdse_products(profile)
    rows = parse_cdse_products(response_json, profile, source_url=url)
    if args.output is None:
        writer = csv.DictWriter(sys.stdout, fieldnames=CDSE_OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CDSE_OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
