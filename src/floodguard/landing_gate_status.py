"""Derive the three public landing gate indicators from validated receipts.

Each indicator is ``met`` only when the canonical validator for its receipt
passes *now*. Nothing is read from a flag someone typed. A missing file or a
failed validator yields ``met=false`` with the reason. The output is the only
source the landing page uses for these three indicators.

- ``qualified_reference_mask``: a qualified-reference release that validates
  with status ``qualified_for_controlled_model_development``.
- ``blind_review_and_adjudication``: a qualified label release whose files
  revalidate through the canonical preflight as eligible for a real experiment.
  In v1 that preflight never returns eligible, so this indicator cannot turn on
  until the independent release-authority validator exists.
- ``frozen_holdout_and_calibration``: a frozen evaluation plan plus a
  self-hash-verified ``final_holdout`` result bound to that plan, to a verified
  custodian opening, and to the same label release as the indicator above.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from floodguard.label_factory.multi_event_preflight import (
    QualifiedReleaseFiles,
    revalidate_qualified_release_files,
)
from floodguard.label_factory.qualified_reference_release import (
    QUALIFIED_STATUS,
    load_qualified_reference_release,
)
from floodguard.observation_evaluation import RESULT_SCHEMA, canonical_sha256, validate_evaluation_plan

STATUS_SCHEMA = "floodguard.landing_gate_status.v1"
CRITERIA = ("qualified_reference_mask", "blind_review_and_adjudication", "frozen_holdout_and_calibration")


class GateNotMet(Exception):
    """Internal signal that a receipt is absent or does not satisfy its gate."""


def build_landing_gate_status(
    *,
    qualified_reference_release: Path | None = None,
    qualified_release_files: QualifiedReleaseFiles | None = None,
    evaluation_plan: Path | None = None,
    final_holdout_result: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Validate the supplied receipts and return the public gate status document."""

    criteria: dict[str, dict[str, Any]] = {}

    def check(criterion: str, validator: str, fn: Callable[[], str]) -> None:
        try:
            receipt = fn()
            criteria[criterion] = {"met": True, "receipt_sha256": receipt, "validator": validator, "reason": "validated"}
        except Exception as error:  # noqa: BLE001 - any failure keeps the gate closed
            criteria[criterion] = {"met": False, "receipt_sha256": None, "validator": validator, "reason": str(error)[:300]}

    def reference() -> str:
        if qualified_reference_release is None:
            raise GateNotMet("no qualified reference release supplied")
        release = load_qualified_reference_release(qualified_reference_release)
        if release["release_status"] != QUALIFIED_STATUS:
            raise GateNotMet(f"reference release status is {release['release_status']}")
        return release["release_sha256"]

    label_gate: dict[str, Any] = {}

    def blind_review() -> str:
        if qualified_release_files is None:
            raise GateNotMet("no qualified label release supplied")
        result = revalidate_qualified_release_files(qualified_release_files)
        if result.get("eligible_for_real_experiment") is not True:
            raise GateNotMet(f"label release preflight status is {result.get('status')}")
        label_gate.update(result)
        return result["qualified_label_release_sha256"]

    def holdout() -> str:
        if evaluation_plan is None or final_holdout_result is None:
            raise GateNotMet("no frozen plan and final-holdout result supplied")
        if not label_gate:
            raise GateNotMet("blind review gate is not met, so no final holdout can count")
        plan = validate_evaluation_plan(json.loads(evaluation_plan.read_text(encoding="utf-8")), require_frozen=True)
        result = json.loads(final_holdout_result.read_text(encoding="utf-8"))
        body = {k: v for k, v in result.items() if k != "result_sha256"}
        if result.get("schema") != RESULT_SCHEMA or result.get("result_sha256") != canonical_sha256(body):
            raise GateNotMet("final-holdout result self-hash does not verify")
        if result.get("role") != "final_holdout" or not result.get("holdout_opening_receipt_sha256"):
            raise GateNotMet("result is not a custodian-opened final holdout")
        if result.get("plan_sha256") != canonical_sha256(plan):
            raise GateNotMet("result was not produced under this frozen plan")
        if result.get("qualified_label_release_sha256") != label_gate["qualified_label_release_sha256"]:
            raise GateNotMet("result used a different label release")
        return result["result_sha256"]

    check("qualified_reference_mask", "qualified_reference_release.validate_qualified_reference_release", reference)
    check("blind_review_and_adjudication", "multi_event_preflight.revalidate_qualified_release_files", blind_review)
    check("frozen_holdout_and_calibration", "observation_evaluation (frozen plan + final_holdout result)", holdout)
    return {
        "schema": STATUS_SCHEMA,
        "generated_utc": generated_at_utc or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "criteria": {name: criteria[name] for name in CRITERIA},
        "official_warning": False,
        "operational_status": "non_operational",
    }
