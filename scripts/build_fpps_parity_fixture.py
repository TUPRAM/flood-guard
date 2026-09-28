"""Write the FPPS parity fixture shared by the Python and TypeScript scoring tests.

It also carries the per-class recommended actions from ``floodguard.briefs`` so the web
action playbook (``apps/web/src/lib/action-playbook.ts``) keeps the same headline wording.

The fixture freezes inputs and the outputs of ``floodguard.scoring.score_subdistricts``
so the web port (``apps/web/src/lib/fpps.ts``) can be checked against the Python
engine without running Python in the browser test suite. ``tests/test_fpps_parity_fixture.py``
fails when the Python engine and the stored fixture drift apart; rerun this script
after an intentional scoring change.

Usage:
    uv run python scripts/build_fpps_parity_fixture.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from floodguard.briefs import RECOMMENDED_ACTIONS, THAI_RECOMMENDED_ACTIONS
from floodguard.scoring import DEFAULT_WEIGHTS, SCORE_COMPONENTS, score_subdistricts

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "fpps_parity_cases.json"

# (flood, exposure, access, road, vulnerability, confidence): each row targets one branch of
# assign_action_class or a threshold edge (FPPS 35, exposure 70/65, access 70/55/50, road 75).
CASES: tuple[tuple[float, float, float, float, float, str], ...] = (
    (90, 80, 75, 40, 50, "high"),
    (90, 80, 75, 40, 50, "low"),
    (90, 70, 70, 40, 50, "medium"),
    (80, 40, 60, 80, 30, "medium"),
    (80, 40, 55, 75, 30, "high"),
    (70, 66, 52, 20, 40, "medium"),
    (70, 65, 50, 20, 40, "medium"),
    (60, 30, 30, 30, 90, "medium"),
    (10, 10, 10, 10, 10, "high"),
    (35, 35, 35, 35, 35, "medium"),
    (34.99, 35, 35, 35, 35, "medium"),
    (0, 0, 0, 0, 0, "medium"),
    (100, 100, 100, 100, 100, "high"),
    (12.345, 67.891, 23.456, 88.8, 4.2, "medium"),
    (50, 90, 40, 20, 90, "high"),
)

ALT_WEIGHTS: dict[str, float] = {
    "flood_likelihood_0_100": 2,
    "exposure_0_100": 1,
    "access_gap_0_100": 1,
    "road_criticality_0_100": 0,
    "vulnerability_context_0_100": 1,
}


def _frame() -> pd.DataFrame:
    rows = []
    for index, (*values, confidence) in enumerate(CASES):
        row: dict[str, object] = {
            "subdistrict_id": f"case_{index:02d}",
            "subdistrict_name": f"Case {index:02d}",
            "confidence_class": confidence,
        }
        row.update(dict(zip(SCORE_COMPONENTS, values, strict=True)))
        rows.append(row)
    return pd.DataFrame(rows)


def _outputs(weights: dict[str, float] | None) -> list[dict[str, object]]:
    scored = score_subdistricts(_frame(), weights)
    return [
        {
            "subdistrict_id": row.subdistrict_id,
            "fpps_0_100": float(row.fpps_0_100),
            "action_class": row.action_class,
            "action_reason_code": row.action_reason_code,
            "top_reason": row.top_reason,
        }
        for row in scored.itertuples()
    ]


def build_fixture() -> dict[str, object]:
    """Return the parity fixture payload from the current Python scoring engine."""

    frame = _frame()
    return {
        "generated_by": "scripts/build_fpps_parity_fixture.py",
        "engine": "floodguard.scoring.score_subdistricts",
        "components": list(SCORE_COMPONENTS),
        "default_weights": DEFAULT_WEIGHTS,
        "inputs": json.loads(frame.to_json(orient="records")),
        "default_outputs": _outputs(None),
        "alt_weights": ALT_WEIGHTS,
        "alt_outputs": _outputs(ALT_WEIGHTS),
        "recommended_actions": {"en": RECOMMENDED_ACTIONS, "th": THAI_RECOMMENDED_ACTIONS},
    }


def main() -> None:
    FIXTURE_PATH.write_text(json.dumps(build_fixture(), indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {FIXTURE_PATH}")


if __name__ == "__main__":
    main()
