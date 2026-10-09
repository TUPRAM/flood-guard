"""Apply the smallest size of a gap (decision log R41) to the committed age comparison over the ensemble.

Protocol v1a lets a gap between age groups be stated when the bounds of the difference exclude zero and 60 percent
of the cells carry one sign. It sets no smallest size, and a difference of a millionth of a point met it. On
9 October 2026 the owners decided that a gap is stated only when the difference nearest to zero is at least one
percentage point. This script applies that to the committed record of the ensemble run and writes what may be
said now. It computes no access run: every figure is read from the record it names. Report-only.

Example::

    python scripts/build_equity_smallest_size.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import equity_by_age as eba  # noqa: E402

RECORD = "outputs/equity_by_age/se1_mae_sai_ensemble_v1.json"
OUTPUT = "outputs/equity_by_age/se1_mae_sai_ensemble_smallest_size_v1.json"
OUTCOMES = ("loses_a_hospital_within_30_minutes", "loses_every_road_route")


def main() -> None:
    source = ROOT / RECORD
    record = json.loads(source.read_text(encoding="utf-8"))

    def restated(block: dict) -> dict:
        return {outcome: {comparison: eba.with_smallest_size(block[outcome][comparison]["rule"]) for comparison in eba.COMPARISONS}
                for outcome in OUTCOMES}

    by_tambon = {unit_id: {"unit_name_en": block["unit_name_en"], **restated(block)} for unit_id, block in record["by_tambon"].items()}
    result = {
        "schema": "floodguard.equity_by_age_smallest_size.v1",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_timestamp": record["source_timestamp"],
        "confidence_class": record["confidence_class"],
        "confidence_basis": record["confidence_basis"],
        "operational_status": "non_operational", "official_warning": False, "can_feed_decision_layer": False,
        "what_this_is": "The age comparison of case SE1 over the 180 cells of the ensemble, restated with a smallest size for a gap. Report-only; no access run was made for it.",
        "label": record["label"],
        "rule": {"of_the_protocol": record["rule"]["gap_sentence_requires"],
                 "smallest_size": "the difference nearest to zero, among the cells, is at least one percentage point",
                 "smallest_size_share": eba.MIN_GAP_SHARE,
                 "decided": "by the owners on 9 October 2026 (decision log R41); protocol v1a is not edited",
                 "sentence_when_the_protocol_rule_is_met_and_the_size_is_not": eba.SMALL_GAP_SENTENCE},
        "made_from": {"path": RECORD, "sha256": hashlib.sha256(source.read_bytes()).hexdigest()},
        "whole_frame": restated(record["whole_frame"]),
        "by_tambon": by_tambon,
        "where_a_gap_may_be_stated": sorted(
            f"{unit_id}:{outcome}:{comparison}" for unit_id, block in by_tambon.items() for outcome in OUTCOMES
            for comparison in eba.COMPARISONS if block[outcome][comparison]["may_state_a_gap"]),
        "where_the_protocol_rule_alone_was_met": record["tambons_where_a_gap_may_be_stated"],
        "assumptions": record["assumptions"],
        "limits": [*record["limits"], "The smallest size is a reading of the owners, written in the decision log; the signed protocol states none."],
    }
    (ROOT / OUTPUT).write_bytes((json.dumps(result, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
    for outcome in OUTCOMES:
        for comparison in eba.COMPARISONS:
            block = result["whole_frame"][outcome][comparison]
            print("district", outcome, comparison, block["may_state_a_gap"], block["smallest_difference"], block["sentence"])
    print(result["where_a_gap_may_be_stated"])


if __name__ == "__main__":
    main()
