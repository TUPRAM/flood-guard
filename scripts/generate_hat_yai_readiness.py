"""Generate or validate the fail-closed Hat Yai readiness artifacts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.hat_yai_readiness import (  # noqa: E402
    HatYaiReadinessError,
    build_hat_yai_readiness_receipt,
    load_hat_yai_readiness_receipt,
    write_hat_yai_readiness_outputs,
)


def main() -> None:
    """Build the pinned status artifacts, or validate existing evidence."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cdse-metadata",
        type=Path,
        default=REPO_ROOT / "outputs" / "cdse_hat_yai_2025_metadata.csv",
    )
    parser.add_argument(
        "--ingestion-manifest",
        type=Path,
        default=REPO_ROOT / "outputs" / "real_data_ingestion_manifest.csv",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=REPO_ROOT / "outputs" / "hat_yai_readiness.json",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=REPO_ROOT / "outputs" / "hat_yai_readiness.md",
    )
    parser.add_argument(
        "--generated-at",
        default=None,
        help="Explicit ISO-8601 UTC time for reproducible generation.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate the existing JSON receipt and pinned inputs without writing.",
    )
    args = parser.parse_args()

    try:
        if args.check:
            receipt = load_hat_yai_readiness_receipt(
                args.json_output,
                cdse_metadata_path=args.cdse_metadata,
                ingestion_manifest_path=args.ingestion_manifest,
            )
            print(
                "VALID: Hat Yai remains fail-closed "
                f"({receipt['reason_blocked']}; receipt_sha256={receipt['receipt_sha256']})"
            )
            return
        generated_at = args.generated_at or datetime.now(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
        receipt = build_hat_yai_readiness_receipt(
            args.cdse_metadata,
            args.ingestion_manifest,
            generated_at=generated_at,
        )
        written = write_hat_yai_readiness_outputs(
            receipt,
            json_output_path=args.json_output,
            markdown_output_path=args.summary_output,
        )
    except HatYaiReadinessError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    for path in written:
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
