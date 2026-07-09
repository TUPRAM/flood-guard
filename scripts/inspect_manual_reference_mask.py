"""Inspect the manual QGIS weak-reference mask outside Git."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.manual_reference import (  # noqa: E402
    DEFAULT_MANUAL_REFERENCE_HINT,
    DEFAULT_MANUAL_REFERENCE_LAYER,
    DEFAULT_MANUAL_REFERENCE_PATH,
    ManualReferenceError,
    write_manual_reference_manifest,
)


def main(argv: list[str] | None = None) -> int:
    """Run the manual weak-reference inspection workflow."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reference-path",
        type=Path,
        default=DEFAULT_MANUAL_REFERENCE_PATH,
        help="Local GeoPackage path outside Git.",
    )
    parser.add_argument(
        "--layer-name",
        default=DEFAULT_MANUAL_REFERENCE_LAYER,
        help="GeoPackage feature layer name.",
    )
    parser.add_argument(
        "--local-path-hint",
        default=DEFAULT_MANUAL_REFERENCE_HINT,
        help="Redacted local path hint to commit in metadata.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "outputs" / "manual_reference_mask_manifest.csv",
    )
    parser.add_argument(
        "--require-existing",
        action="store_true",
        help="Fail instead of writing a blocked skeleton row when the GeoPackage is missing.",
    )
    parser.add_argument(
        "--inspected-at",
        default=None,
        help="Optional fixed UTC timestamp for reproducible tests.",
    )
    args = parser.parse_args(argv)

    try:
        written = write_manual_reference_manifest(
            args.output,
            reference_path=args.reference_path,
            layer_name=args.layer_name,
            local_path_hint=args.local_path_hint,
            inspected_at_utc=args.inspected_at,
            allow_missing=not args.require_existing,
        )
    except ManualReferenceError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
