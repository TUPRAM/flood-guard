"""Build a write-once internal active-learning operator queue package."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.operator_queue import (  # noqa: E402
    OperatorQueueError,
    write_operator_queue_package,
)


def main() -> None:
    """Create the operator-only CSV plus checksum/self-hashed manifest."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquisition-manifest", type=Path, required=True)
    parser.add_argument("--context-evidence", type=Path)
    parser.add_argument("--weak-summary", type=Path)
    parser.add_argument("--preview-manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--generated-at-utc",
        help="Optional fixed UTC timestamp for reproducible controlled runs.",
    )
    args = parser.parse_args()
    try:
        written = write_operator_queue_package(
            args.acquisition_manifest,
            output_dir=args.output_dir,
            context_evidence=args.context_evidence,
            weak_summary=args.weak_summary,
            preview_manifest=args.preview_manifest,
            generated_at_utc=args.generated_at_utc,
        )
    except (OperatorQueueError, OSError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print(f"Wrote operator queue: {written['queue']}")
    print(f"Wrote operator manifest: {written['manifest']}")
    print("Safety: operator-only; flood truth=false; decision=false; FPPS=false; warning=false")


if __name__ == "__main__":
    main()
