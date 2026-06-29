"""Generate sample FloodGuard priority scores from fixture data."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.scoring import score_subdistricts  # noqa: E402

OUTPUT_COLUMNS = [
    "subdistrict_id",
    "subdistrict_name",
    "fpps_0_100",
    "action_class",
    "top_reason",
    "confidence_class",
    "source_name",
    "source_timestamp",
    "assumptions",
]


def main() -> None:
    """Score the sample fixture and write a dashboard-ready CSV."""

    input_path = REPO_ROOT / "tests" / "fixtures" / "sample_population.csv"
    output_path = REPO_ROOT / "outputs" / "sample_priority_scores.csv"

    frame = pd.read_csv(input_path)
    scored = score_subdistricts(frame)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    scored.loc[:, OUTPUT_COLUMNS].to_csv(output_path, index=False)
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
