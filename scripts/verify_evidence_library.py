"""Verify a completed public evidence library and optional local lineage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from floodguard.evidence_catalog import canonical_bytes
from floodguard.evidence_validation import verify_evidence_library


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-dir", type=Path, required=True)
    parser.add_argument("--local-dir", type=Path)
    parser.add_argument("--output-receipt", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_receipt.resolve()
    repository = Path(__file__).resolve().parents[1]
    if output.is_relative_to(repository) or output.is_relative_to(
        args.public_dir.resolve()
    ):
        parser.error(
            "The verification receipt must be outside Git and the public export."
        )
    try:
        receipt = verify_evidence_library(args.public_dir, local_dir=args.local_dir)
    except (ValueError, OSError, KeyError, TypeError) as error:
        receipt = {
            "schema_version": "floodguard.evidence_export_verification.v1",
            "status": "failed",
            "error": str(error),
            "scientific_or_operational_acceptance": False,
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(canonical_bytes(receipt))
        print(json.dumps(receipt, indent=2))
        raise SystemExit(1) from error
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical_bytes(receipt))
    print(
        json.dumps(
            {key: value for key, value in receipt.items() if key != "files"}, indent=2
        )
    )


if __name__ == "__main__":
    main()
