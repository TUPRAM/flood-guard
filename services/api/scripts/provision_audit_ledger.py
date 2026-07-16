"""Provision the pilot audit ledger and external genesis anchor exactly once."""

from __future__ import annotations

import argparse
from pathlib import Path

from floodguard_api.pilot import PilotKeyring, provision_audit_ledger


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create an empty audit JSONL file and separately mounted signed genesis anchor."
        )
    )
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--anchor", required=True, type=Path)
    args = parser.parse_args()
    provision_audit_ledger(
        ledger_path=args.ledger,
        anchor_path=args.anchor,
        keyring=PilotKeyring.from_environment(),
    )
    print("Pilot audit genesis provisioned and verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
