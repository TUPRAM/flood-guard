"""Check reference-mask legal gates before real validation or ML work."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.reference_gates import (  # noqa: E402
    build_reference_gate_report,
    default_reference_gate_rows,
    write_reference_gate_report,
)


def main() -> None:
    """Run the reference-mask legal gate check."""

    parser = argparse.ArgumentParser(
        description=(
            "Check whether reference-mask provider responses clear local "
            "validation or ML-label gates. This script never downloads data."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        help=(
            "Optional CSV with reference gate fields. When omitted, the current "
            "blocked provider-response rows are used."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional CSV output path for the gate report.",
    )
    parser.add_argument(
        "--study-area-contains",
        default=None,
        help="Optional case-insensitive study-area substring filter.",
    )
    parser.add_argument(
        "--allow-blocked",
        action="store_true",
        help="Exit 0 even when all rows remain blocked; useful for dry-run reviews.",
    )
    args = parser.parse_args()

    source = (
        pd.read_csv(args.input, dtype=str).fillna("")
        if args.input is not None
        else default_reference_gate_rows()
    )

    if args.output is not None:
        written = write_reference_gate_report(
            source,
            args.output,
            study_area_contains=args.study_area_contains,
        )
        report = pd.read_csv(written, dtype=str).fillna("")
        print(f"Wrote {written}")
    else:
        report = build_reference_gate_report(
            source,
            study_area_contains=args.study_area_contains,
        )

    display_columns = [
        "source_name",
        "reference_validation_allowed",
        "ml_label_allowed",
        "gate_status",
        "reason_blocked",
    ]
    print(report.loc[:, display_columns].to_string(index=False))

    any_ready = report["reference_validation_allowed"].map(_truthy).any()
    if any_ready or args.allow_blocked:
        raise SystemExit(0)
    raise SystemExit(1)


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


if __name__ == "__main__":
    main()
