"""Derive the review checks of the GEOID M1 benchmark from committed files.

Reads the committed held-out summary and the tuning log and writes
outputs/geoid_m1_benchmark_v2_derived_checks.json: the held-out score with
each test tile left out, a tile bootstrap, what the declined tiles hold, the
Otsu comparator across the declared grid, the sign of the M1-literal
threshold and the Dice figures. No tile is opened, no score changes and
nothing is selected. The output is a pure function of the two inputs, so
running the script again writes the same bytes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import geoid_m1_benchmark as bench  # noqa: E402
from floodguard import geoid_m1_review as review  # noqa: E402


def build(root: Path) -> dict[str, object]:
    """Compute the derived checks from the files under ``root``."""

    summary_bytes = (root / review.SUMMARY_FILE).read_bytes()
    log_bytes = (root / review.TUNING_LOG_FILE).read_bytes()
    summary = json.loads(summary_bytes)
    if summary["provenance"]["tuning_log_sha256"] != bench.bytes_sha256(log_bytes):
        raise SystemExit("The tuning log is not the one the summary was computed with")
    records = [json.loads(line) for line in log_bytes.decode("utf-8").splitlines()]
    return review.derived_checks(
        summary,
        records,
        summary_sha256=bench.bytes_sha256(summary_bytes),
        tuning_log_sha256=bench.bytes_sha256(log_bytes),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write; fail if the committed file differs from a fresh derivation.",
    )
    arguments = parser.parse_args()
    data = bench.canonical_json_bytes(build(ROOT))
    target = ROOT / review.DERIVED_CHECKS_FILE
    if arguments.check:
        if not target.is_file() or target.read_bytes() != data:
            raise SystemExit(f"{review.DERIVED_CHECKS_FILE} differs from a fresh derivation")
        print(f"{review.DERIVED_CHECKS_FILE} matches a fresh derivation")
        return
    target.write_bytes(data)
    bar = json.loads(data)["t2_skill_bar"]["m1_v2_test"]
    print(f"wrote {review.DERIVED_CHECKS_FILE}")
    print(f"reading: {bar['reading']} (abstained cell share {bar['abstained_cell_share']})")


if __name__ == "__main__":
    main()
