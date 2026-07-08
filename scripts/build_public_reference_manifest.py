"""Build public/open data candidate manifests without downloading source assets."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.public_reference_inventory import (  # noqa: E402
    write_public_reference_manifest,
    write_sentinel_asia_product_links,
)


def main(argv: list[str] | None = None) -> int:
    """Run the public reference candidate inventory workflow."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "outputs" / "public_reference_candidate_manifest.csv",
        help="Output CSV for all public source candidates.",
    )
    parser.add_argument(
        "--sentinel-asia-products-output",
        type=Path,
        default=REPO_ROOT / "outputs" / "sentinel_asia_public_product_links.csv",
        help="Output CSV for scraped Sentinel Asia public product links.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Write only seed source rows; do not fetch the Sentinel Asia page.",
    )
    parser.add_argument(
        "--retrieved-at",
        default=None,
        help="Optional fixed UTC timestamp for reproducible tests.",
    )
    args = parser.parse_args(argv)

    include_live_links = not args.offline
    manifest_path = write_public_reference_manifest(
        args.output,
        include_sentinel_asia_products=include_live_links,
        retrieved_at_utc=args.retrieved_at,
    )
    print(f"Wrote {manifest_path}")

    if include_live_links:
        product_path = write_sentinel_asia_product_links(
            args.sentinel_asia_products_output,
            retrieved_at_utc=args.retrieved_at,
        )
        print(f"Wrote {product_path}")
    else:
        print("Skipped live Sentinel Asia product scrape because --offline was set.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
