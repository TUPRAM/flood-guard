"""Rebuild the landing page's three gate indicators from validated receipts.

Run on the machine that holds the external workspace. With no receipts every
indicator stays ``met=false``; that is the correct current state.

    uv run python scripts/build_landing_gate_status.py \
      --qualified-reference-release <ext>/reference/qualified_reference_release.json \
      --label-release-dir <ext>/label_release/mae_sai_v1 \
      --evaluation-plan <ext>/evaluation/plan_frozen.json \
      --final-holdout-result <ext>/evaluation/final_holdout_result.json

``--label-release-dir`` must contain ``release.json``, ``formal_review.json``,
``human_role_package/``, ``reviewer_calibration.json``, ``labelset_manifest.json``,
``labelset_validation.json``, ``review_pair_*.json``, ``qualified_reference.json``,
``reference_raster.tif`` and ``analysis_grid.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from floodguard.label_factory.multi_event_preflight import QualifiedReleaseFiles  # noqa: E402
from floodguard.landing_gate_status import build_landing_gate_status  # noqa: E402

DEFAULT_OUTPUT = REPO_ROOT / "apps" / "web" / "src" / "lib" / "landing" / "gate-status.json"


def _release_files(directory: Path) -> QualifiedReleaseFiles:
    return QualifiedReleaseFiles(
        release_json=directory / "release.json",
        formal_review_json=directory / "formal_review.json",
        human_role_package=directory / "human_role_package",
        reviewer_calibration=directory / "reviewer_calibration.json",
        labelset_manifest=directory / "labelset_manifest.json",
        labelset_validation=directory / "labelset_validation.json",
        review_pair_json=tuple(sorted(directory.glob("review_pair_*.json"))),
        qualified_reference_json=directory / "qualified_reference.json",
        reference_raster=directory / "reference_raster.tif",
        analysis_grid=directory / "analysis_grid.json",
    )


def main(argv: list[str] | None = None) -> int:
    """Validate supplied receipts and write the public gate status JSON."""

    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--qualified-reference-release", type=Path)
    p.add_argument("--label-release-dir", type=Path)
    p.add_argument("--evaluation-plan", type=Path)
    p.add_argument("--final-holdout-result", type=Path)
    p.add_argument("--generated-at", default=None)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = p.parse_args(argv)

    status = build_landing_gate_status(
        qualified_reference_release=args.qualified_reference_release,
        qualified_release_files=_release_files(args.label_release_dir) if args.label_release_dir else None,
        evaluation_plan=args.evaluation_plan,
        final_holdout_result=args.final_holdout_result,
        generated_at_utc=args.generated_at,
    )
    args.output.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    for name, value in status["criteria"].items():
        print(f"{name}: {'MET' if value['met'] else 'not met'} - {value['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
