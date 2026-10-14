"""Write (or check) the weight test of the published case SE1: would the order of the eight tambons change with other weights?

Reads the published planning overlay ``apps/web/public/planning-overlays/mae-sai-2024/se1.json`` and writes

* ``outputs/fpps_weight_sensitivity/se1_mae_sai_v1.json``, the report, and
* ``apps/web/src/lib/policy-weight-sensitivity.json``, the same report for the policy page.

Report only: it changes no score, no weight and no class, and it is not part of the planning protocol.

    python scripts/build_fpps_weight_sensitivity.py           # write both files
    python scripts/build_fpps_weight_sensitivity.py --check   # exit 1 if a committed file is stale
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import fpps_weight_sensitivity as sensitivity  # noqa: E402

CASE = ROOT / "apps" / "web" / "public" / "planning-overlays" / "mae-sai-2024" / "se1.json"
REPORT = ROOT / "outputs" / "fpps_weight_sensitivity" / "se1_mae_sai_v1.json"
PAGE_COPY = ROOT / "apps" / "web" / "src" / "lib" / "policy-weight-sensitivity.json"


def build() -> dict:
    """The report for the published case, with the case's own labels carried beside the figures."""

    data = CASE.read_bytes()
    case = json.loads(data)
    rows = case["rows"]
    values = {row["unit_id"]: {name: row["components"][name]["value_0_100"] for name in sensitivity.COMPONENTS} for row in rows}
    report = sensitivity.assess(values)
    # The scores added up here are the published ones, to the two decimals the case prints.
    for row in rows:
        if abs(report["published"]["scores"][row["unit_id"]] - row["fpps_0_100"]) > 0.005:
            raise SystemExit(f"{row['unit_id']}: the components do not add up to the published score")
    return {
        **report,
        "case": {"id": "SE1", "path": CASE.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest(),
                 "lane": rows[0]["lane"], "source_timestamp": case["source_timestamp"], "dataset_mode": case["dataset_mode"],
                 "official_warning": case["official_warning"],
                 "confidence": "medium, declared for a scenario; the weight test adds no confidence to it"},
        "units": {row["unit_id"]: {"en": row["unit_name_en"], "th": row["unit_name_th"]} for row in rows},
        "assumptions": [
            "Case SE1 is a scenario: every area mapped as flooded in the 2024 season is treated as flooded at once. It is not an observation of any day.",
            "Only the weights change. The components, their anchors and the roads closed are those of the published case.",
        ],
    }


def text(report: dict) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--check", action="store_true", help="write nothing; fail if a committed file is stale")
    arguments = parser.parse_args()
    wanted = text(build())
    stale = [path for path in (REPORT, PAGE_COPY) if not path.exists() or path.read_bytes().decode("utf-8") != wanted]
    if arguments.check:
        for path in stale:
            print(f"{path.relative_to(ROOT).as_posix()} is stale: run scripts/build_fpps_weight_sensitivity.py")
        if not stale:
            print("the weight test matches the published case")
        return 1 if stale else 0
    for path in (REPORT, PAGE_COPY):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(wanted.encode("utf-8"))
        print(f"wrote {path.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
