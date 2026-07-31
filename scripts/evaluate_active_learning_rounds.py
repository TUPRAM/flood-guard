"""Compare active versus random review rounds and apply fail-fast rules."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.evaluation import (  # noqa: E402
    ActiveLearningEvaluationError,
    write_active_learning_evaluation,
)


def main() -> None:
    """Write equal-cost comparison evidence and the current stop decision."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round-evidence", type=Path, required=True)
    parser.add_argument("--comparison-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    parser.add_argument("--equal-cost-relative-tolerance", type=float, default=0.10)
    parser.add_argument("--minimum-iou-gain", type=float, default=0.0)
    args = parser.parse_args()
    try:
        _comparisons, decision, written = write_active_learning_evaluation(
            args.round_evidence,
            comparison_output_path=args.comparison_output,
            summary_output_path=args.summary_output,
            equal_cost_relative_tolerance=args.equal_cost_relative_tolerance,
            minimum_iou_gain=args.minimum_iou_gain,
        )
    except (ActiveLearningEvaluationError, OSError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    for label, path in written.items():
        print(f"Wrote {label}: {path}")
    print(f"Decision: {decision.status}")


if __name__ == "__main__":
    main()
