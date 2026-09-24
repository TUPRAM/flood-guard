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
import math
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from floodguard.label_factory.multi_event_preflight import (
    QualifiedReleaseFiles,
    revalidate_qualified_release_files,
)
from floodguard.label_factory.qualified_reference_release import (
    QUALIFIED_STATUS,
    load_qualified_reference_release,
)
from floodguard.observation_evaluation import (
    RESULT_SCHEMA,
    canonical_sha256,
    validate_evaluation_plan,
)

STATUS_SCHEMA = "floodguard.landing_gate_status.v1"
CRITERIA = ("qualified_reference_mask", "blind_review_and_adjudication", "frozen_holdout_and_calibration")
AUTOMATED_CRITERIA = (
    "automated_optical_reference",
    "automated_cross_review",
    "preregistered_holdout_evaluation",
)


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


def build_automated_landing_gate_status(
    *,
    preregistration: Path | None = None,
    input_manifest: Path | None = None,
    reference_receipt: Path | None = None,
    reference_raster: Path | None = None,
    final_holdout_result: Path | None = None,
    development_result: Path | None = None,
    holdout_marker: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Validate the separately named automated receipts for public indicators."""

    from floodguard.observation_evaluation import (
        validate_automated_evaluation_result,
        validate_automated_preregistration,
        verify_automated_preregistration_commit,
    )

    repo_root = Path(__file__).resolve().parents[2]
    criteria: dict[str, dict[str, Any]] = {}
    verified_plan: dict[str, Any] | None = None
    verified_reference: dict[str, Any] | None = None
    candidate_agreement: dict[str, dict[str, Any]] = {}

    def check(criterion: str, validator: str, fn: Callable[[], str]) -> None:
        try:
            receipt = fn()
            criteria[criterion] = {"met": True, "receipt_sha256": receipt, "validator": validator, "reason": "validated"}
        except Exception as error:  # noqa: BLE001 - invalid or absent receipts keep each indicator off
            criteria[criterion] = {"met": False, "receipt_sha256": None, "validator": validator, "reason": str(error)[:300]}

    def optical_reference() -> str:
        nonlocal verified_plan, verified_reference
        if preregistration is None or input_manifest is None or reference_receipt is None or reference_raster is None:
            raise GateNotMet("pre-registration, asset manifest, optical reference receipt and label raster are required")
        if not preregistration.is_file():
            raise GateNotMet("pre-registration file is unavailable")
        if not reference_raster.is_file():
            raise GateNotMet("automated optical label raster is unavailable")
        from floodguard.automated_reference import validate_automated_reference_receipt

        plan = validate_automated_preregistration(json.loads(preregistration.read_text(encoding="utf-8")))
        reference = validate_automated_reference_receipt(
            reference_receipt, manifest=input_manifest, raster_path=reference_raster,
        )
        if reference.get("preregistration_sha256") != plan["preregistration_sha256"]:
            raise GateNotMet("optical reference uses a different pre-registration")
        verify_automated_preregistration_commit(plan, reference.get("preregistration_commit"), repo_root)
        verified_plan, verified_reference = plan, reference
        return reference["receipt_sha256"]

    def cross_review() -> str:
        if verified_plan is None or verified_reference is None:
            raise GateNotMet("optical reference receipt did not verify")
        observed = verified_reference["ab_agreement"]
        limits = verified_plan["cross_review_limits"]
        dice, kappa = observed["water_dice"], observed["cohen_kappa"]
        if not all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) for value in (dice, kappa)):
            raise GateNotMet("A/B agreement metrics are unavailable")
        if not 0 <= dice <= 1 or not -1 <= kappa <= 1:
            raise GateNotMet("A/B agreement metrics are outside their valid ranges")
        if dice < limits["min_water_dice"] or kappa < limits["min_cohen_kappa"]:
            raise GateNotMet(
                f"A/B agreement below pre-registered limits: water Dice {dice:.3f} "
                f"(min {limits['min_water_dice']:.3f}), kappa {kappa:.3f} "
                f"(min {limits['min_cohen_kappa']:.3f})"
            )
        return verified_reference["receipt_sha256"]

    def holdout() -> str:
        if verified_plan is None or verified_reference is None:
            raise GateNotMet("optical reference receipt did not verify")
        if final_holdout_result is None:
            raise GateNotMet("no automated final-holdout result supplied")
        if not final_holdout_result.is_file():
            raise GateNotMet("automated final-holdout result file is unavailable")
        if development_result is None or holdout_marker is None:
            raise GateNotMet("development receipt and external holdout-consumption marker are required")
        if not development_result.is_file() or not holdout_marker.is_file():
            raise GateNotMet("development receipt or external holdout-consumption marker is unavailable")
        result = validate_automated_evaluation_result(
            json.loads(final_holdout_result.read_text(encoding="utf-8")),
            verified_plan,
            verified_reference,
            development_result=development_result,
            holdout_marker=holdout_marker,
        )
        if result["role"] != "final_holdout":
            raise GateNotMet("automated result is not final_holdout")
        verify_automated_preregistration_commit(
            verified_plan, result.get("preregistration_commit_sha"), repo_root,
        )
        scores: dict[str, dict[str, Any]] = {}
        for product in verified_plan["candidate_products"]:
            product_id = product["product_id"]
            candidate = result["candidate_results"][product_id]
            metrics = candidate["metrics"]
            for name in ("iou", "evaluated_coverage"):
                value = metrics[name]
                if value is not None and (
                    not isinstance(value, (int, float)) or isinstance(value, bool)
                    or not math.isfinite(value) or not 0 <= value <= 1
                ):
                    raise GateNotMet(f"candidate {product_id} has invalid {name}")
            scores[product_id] = {
                "processing_variant": candidate["processing_variant"],
                "iou": metrics["iou"],
                "evaluated_coverage": metrics["evaluated_coverage"],
                "meets_predeclared_limits": candidate["acceptance"]["meets_predeclared_limits"],
            }
        candidate_agreement.update(scores)
        return result["result_sha256"]

    check("automated_optical_reference", "automated_reference.validate_automated_reference_receipt", optical_reference)
    check("automated_cross_review", "pre-registered A/B Dice and Cohen's kappa", cross_review)
    check("preregistered_holdout_evaluation", "observation_evaluation.validate_automated_evaluation_result", holdout)
    return {
        "schema": STATUS_SCHEMA,
        "track": "automated",
        "generated_utc": generated_at_utc or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_timestamp": verified_plan["source"]["event_sensing_utc"] if verified_plan else None,
        "confidence": (
            "limited: single-event automated optical reference with failed two-method agreement"
            if verified_reference else "unverified: automated optical reference receipt is unavailable"
        ),
        "assumptions": [
            "The optical map is automated research evidence, not human flood truth.",
            "A verified evaluation measures agreement with that map, not accuracy.",
        ],
        "criteria": {name: criteria[name] for name in AUTOMATED_CRITERIA},
        "candidate_agreement": candidate_agreement,
        "human_reviewed": False,
        "can_feed_decision_layer": False,
        "official_warning": False,
        "operational_status": "non_operational",
    }
