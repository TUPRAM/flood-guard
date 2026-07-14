"""Train FloodGuard's strict spatial query committee and write audit artifacts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.committee import (  # noqa: E402
    CommitteeDependencyError,
    CommitteeError,
    train_and_write_query_committee,
)
from floodguard.label_factory.versioning import (  # noqa: E402
    LabelsetVersionError,
    load_labelset_manifest,
)


def main() -> None:
    """Run a new, non-overwriting query-committee training job."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--training-csv",
        type=Path,
        required=True,
        help="Reviewed/adjudicated binary training rows with frozen spatial groups.",
    )
    parser.add_argument(
        "--pool-csv",
        type=Path,
        required=True,
        help="Unreviewed training-and-query-pool feature rows to score.",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        required=True,
        help="A new directory; existing paths are never overwritten.",
    )
    parser.add_argument(
        "--labelset-manifest",
        type=Path,
        required=True,
        help="Verified frozen labelset JSON; version and hash are read from it.",
    )
    parser.add_argument(
        "--training-derivation-manifest",
        type=Path,
        required=True,
        help="Self-hashed manifest generated with the exact training CSV.",
    )
    parser.add_argument(
        "--release-validation-receipt",
        type=Path,
        required=True,
        help="Code-generated passing receipt bound to the frozen labelset.",
    )
    parser.add_argument("--feature-schema-version", default="sar_change_v2")
    parser.add_argument(
        "--feature-columns",
        nargs="+",
        default=None,
        help="Schema-ordered columns. Defaults to all required schema features.",
    )
    parser.add_argument("--target-column", default="binary_target")
    parser.add_argument("--group-column", default="spatial_group_id")
    parser.add_argument("--splits", type=int, default=5)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--random-seed", type=int, default=0)
    parser.add_argument("--run-id")
    parser.add_argument("--logistic-epochs", type=int, default=1_000)
    parser.add_argument("--logistic-learning-rate", type=float, default=0.08)
    parser.add_argument("--logistic-l2", type=float, default=0.001)
    args = parser.parse_args()

    try:
        labelset = load_labelset_manifest(args.labelset_manifest)
        written = train_and_write_query_committee(
            args.training_csv,
            args.pool_csv,
            args.output_directory,
            training_derivation_manifest=args.training_derivation_manifest,
            release_validation_receipt=args.release_validation_receipt,
            labelset_manifest=args.labelset_manifest,
            labelset_version=labelset.labelset_id,
            labelset_manifest_sha256=labelset.manifest_sha256,
            feature_schema_version=args.feature_schema_version,
            feature_order=args.feature_columns,
            target_column=args.target_column,
            group_column=args.group_column,
            n_splits=args.splits,
            n_repeats=args.repeats,
            random_seed=args.random_seed,
            run_id=args.run_id,
            logistic_epochs=args.logistic_epochs,
            logistic_learning_rate=args.logistic_learning_rate,
            logistic_l2=args.logistic_l2,
        )
    except (CommitteeError, CommitteeDependencyError, LabelsetVersionError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    for label, path in written.as_dict().items():
        print(f"Wrote {label}: {path}")


if __name__ == "__main__":
    main()
