"""Build an immutable queue for reviewer disagreements and ambiguous reviews."""

from __future__ import annotations

import argparse
from datetime import datetime
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.adjudication import (  # noqa: E402
    AdjudicationError,
    build_adjudication_queue,
    pair_locked_annotations,
)
from floodguard.label_factory.annotations import (  # noqa: E402
    AnnotationValidationError,
    load_annotation_log,
)
from floodguard.label_factory.review_workflow import (  # noqa: E402
    ReviewWorkflowError,
    write_adjudication_queue_csv,
)


def main() -> None:
    """Queue only cases that have an explicit protocol reason."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotation-log", type=Path, required=True)
    parser.add_argument("--reviewer-a-id", required=True)
    parser.add_argument("--reviewer-b-id", required=True)
    parser.add_argument(
        "--created-at-utc",
        required=True,
        help="Explicit timezone-aware queue creation timestamp.",
    )
    parser.add_argument("--queue-prefix", default="ADJQ")
    parser.add_argument("--output-csv", type=Path, required=True)
    args = parser.parse_args()
    try:
        created_at = datetime.fromisoformat(args.created_at_utc.replace("Z", "+00:00"))
        records = load_annotation_log(args.annotation_log)
        pairs = pair_locked_annotations(
            records,
            reviewer_a_id=args.reviewer_a_id,
            reviewer_b_id=args.reviewer_b_id,
        )
        queue = build_adjudication_queue(
            pairs,
            created_at_utc=created_at,
            queue_prefix=args.queue_prefix,
        )
        output = write_adjudication_queue_csv(queue, args.output_csv)
    except (
        ReviewWorkflowError,
        AnnotationValidationError,
        AdjudicationError,
        OSError,
        ValueError,
    ) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print(f"Wrote {len(queue)} adjudication queue item(s): {output}")


if __name__ == "__main__":
    main()
