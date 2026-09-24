"""Validate separately evidenced facility identity, role, entrance and capacity."""

import argparse
import json
from pathlib import Path

from floodguard.evidence_catalog import canonical_bytes, sha256_file
from floodguard.evidence_facility_verification import validate_facility_verification


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--event-date", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    records = json.loads(args.input.read_bytes())
    if len({r["facility_id"] for r in records}) != len(records):
        raise ValueError("Duplicate facility IDs need reconciliation")
    result = {
        "schema_version": "floodguard.facility_verification.v1",
        "input_sha256": sha256_file(args.input),
        "event_date": args.event_date,
        "records": [
            validate_facility_verification(r, event_date=args.event_date)
            for r in records
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(result))
    print(
        f"Validated {len(records)} records; {sum(r['shelter_access_eligible'] for r in result['records'])} eligible shelter destinations"
    )


if __name__ == "__main__":
    main()
