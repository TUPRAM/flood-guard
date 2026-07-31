"""Build an immutable per-query positive-unlabelled weak-reference summary."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.weak_query_summary import (  # noqa: E402
    WeakQuerySummaryError,
    verify_weak_query_summary,
    write_weak_query_summary,
)


def main() -> None:
    """Summarise weak overlap without treating polygon exterior as dry land."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weak-vector", type=Path, required=True)
    parser.add_argument("--weak-source-manifest", type=Path, required=True)
    parser.add_argument("--query-manifest", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument(
        "--generated-at-utc",
        help="Optional timezone-aware generation timestamp for reproducible runs.",
    )
    parser.add_argument(
        "--vector-layer",
        help="Optional layer name for a multi-layer GeoPackage.",
    )
    parser.add_argument(
        "--repair-invalid-geometry",
        action="store_true",
        help=(
            "Apply Shapely make_valid to invalid polygon features and record the "
            "repair in provenance. The default is to fail closed."
        ),
    )
    args = parser.parse_args()
    try:
        written = write_weak_query_summary(
            weak_vector_path=args.weak_vector,
            weak_source_manifest=args.weak_source_manifest,
            query_manifest=args.query_manifest,
            output_directory=args.output_directory,
            vector_layer=args.vector_layer,
            repair_invalid_geometry=args.repair_invalid_geometry,
            generated_at_utc=args.generated_at_utc,
        )
        verified = verify_weak_query_summary(
            summary_csv=written.summary_csv,
            manifest_json=written.manifest_json,
        )
    except (WeakQuerySummaryError, OSError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    for label, path in written.as_dict().items():
        print(f"Wrote {label}: {path}")
    print(f"Verified query rows: {len(verified)}")
    print(
        "Safety: positive-unlabelled/operator-internal only; training=false; "
        "decision layer=false; FPPS=false; warning=false"
    )


if __name__ == "__main__":
    main()
