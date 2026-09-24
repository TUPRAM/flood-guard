"""Frozen-plan, bounded single-event flood observation evaluation.

This module scores a candidate flood-observation raster against a qualified
human reference raster, but only under a frozen, attributable evaluation plan
and a label release that the canonical release validator marks eligible for a
real experiment. It never loosens those gates: a draft plan, a fixture-only
label release, or an unverified final-holdout opening raises
``ObservationEvaluationError`` before any metric is computed.

A passing comparison against the plan's predeclared limits is still not an
accepted observation, FPPS input, or warning. Those need the separate
downstream acceptance receipt.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from typing import Any, Mapping

import numpy as np

from floodguard.label_factory.agreement import compute_boundary_f1
from floodguard.label_factory.contracts import FloodLabel

PLAN_SCHEMA = "floodguard.observation_evaluation_plan.v1"
RESULT_SCHEMA = "floodguard.observation_evaluation_result.v1"
ROLES = ("development", "final_holdout")
PARTITION_EXCLUDED, PARTITION_DEVELOPMENT, PARTITION_FINAL_HOLDOUT = 0, 1, 2
CANDIDATE_DRY, CANDIDATE_FLOOD, CANDIDATE_ABSTAIN = 0, 1, 255
LIMIT_KEYS = ("min_iou", "min_precision", "min_recall", "max_abs_area_error_fraction", "min_evaluated_coverage")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_PLAN_KEYS = {
    "schema", "plan_id", "status", "event_id", "study_area_id", "observation_target", "candidate_products",
    "reference", "partition", "pixel_size_m", "boundary_tolerance_m", "strata", "acceptance_limits", "frozen",
    "assumptions",
}

ASSUMPTIONS = [
    "Positive reference class is temporary flood (code 1); dry land (code 0) is the only negative.",
    "Permanent/pre-existing water, uncertain, unobservable and unreviewed cells are excluded, never scored as dry.",
    "Candidate abstention (255) lowers evaluated coverage; it is not counted as a dry prediction.",
    "Cells inside the partition halo are excluded from both roles.",
    "Meeting predeclared limits is not an accepted observation, FPPS component or warning.",
]


class ObservationEvaluationError(ValueError):
    """Raised when a plan, gate, or input would make the evaluation unsafe."""


def canonical_sha256(value: Any) -> str:
    """Return the SHA-256 of a JSON value serialized with sorted keys and no spaces."""

    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_evaluation_plan(plan: Mapping[str, Any], *, require_frozen: bool) -> dict[str, Any]:
    """Validate an observation evaluation plan.

    A ``draft`` plan may leave acceptance limits and signer fields null. A
    ``frozen`` plan must fill every limit, name the evaluation lead, bind the
    decision-evidence hash and give a UTC freeze time. ``require_frozen=True``
    rejects drafts.
    """

    value = dict(plan)
    if set(value) != _PLAN_KEYS:
        raise ObservationEvaluationError(f"plan fields must be exactly {sorted(_PLAN_KEYS)}")
    if value["schema"] != PLAN_SCHEMA:
        raise ObservationEvaluationError(f"plan schema must be {PLAN_SCHEMA}")
    if value["status"] not in ("draft", "frozen"):
        raise ObservationEvaluationError("plan status must be draft or frozen")
    for key in ("plan_id", "event_id", "study_area_id", "observation_target"):
        if not isinstance(value[key], str) or not value[key].strip():
            raise ObservationEvaluationError(f"{key} must be a non-empty string")
    partition = value["partition"]
    if set(partition) != {"block_size_m", "halo_m", "seed", "development_fraction"}:
        raise ObservationEvaluationError("partition fields are not exact")
    block, halo, fraction = partition["block_size_m"], partition["halo_m"], partition["development_fraction"]
    if not (_positive(block) and _non_negative(halo) and 2 * halo < block):
        raise ObservationEvaluationError("partition needs block_size_m > 2 * halo_m >= 0")
    if not (isinstance(fraction, (int, float)) and 0 < fraction < 1):
        raise ObservationEvaluationError("development_fraction must lie strictly between 0 and 1")
    if not isinstance(partition["seed"], str) or not partition["seed"]:
        raise ObservationEvaluationError("partition seed must be a non-empty string")
    if not (_positive(value["pixel_size_m"]) and _non_negative(value["boundary_tolerance_m"])):
        raise ObservationEvaluationError("pixel_size_m must be > 0 and boundary_tolerance_m >= 0")
    if not isinstance(value["strata"], list) or not all(isinstance(s, str) and s for s in value["strata"]):
        raise ObservationEvaluationError("strata must be a list of names")
    limits = value["acceptance_limits"]
    if set(limits) != set(LIMIT_KEYS):
        raise ObservationEvaluationError(f"acceptance_limits must be exactly {list(LIMIT_KEYS)}")
    frozen = value["frozen"]
    if set(frozen) != {"frozen_at_utc", "evaluation_lead_person_id", "decision_evidence_sha256"}:
        raise ObservationEvaluationError("frozen block fields are not exact")
    if value["status"] == "frozen":
        for key, limit in limits.items():
            if not isinstance(limit, (int, float)) or isinstance(limit, bool) or not math.isfinite(limit) or not 0 <= limit <= 1:
                raise ObservationEvaluationError(f"frozen plan limit {key} must be a number in [0, 1]")
        if not (isinstance(frozen["frozen_at_utc"], str) and _UTC.fullmatch(frozen["frozen_at_utc"])):
            raise ObservationEvaluationError("frozen_at_utc must be YYYY-MM-DDTHH:MM:SSZ")
        if not (isinstance(frozen["evaluation_lead_person_id"], str) and frozen["evaluation_lead_person_id"].strip()):
            raise ObservationEvaluationError("frozen plan must name evaluation_lead_person_id")
        if not (isinstance(frozen["decision_evidence_sha256"], str) and _SHA256.fullmatch(frozen["decision_evidence_sha256"])):
            raise ObservationEvaluationError("frozen plan must bind decision_evidence_sha256")
        if not value["reference"].get("label_release_id"):
            raise ObservationEvaluationError("frozen plan must name the qualified label release")
    elif require_frozen:
        raise ObservationEvaluationError("evaluation requires a frozen plan; this plan is a draft")
    return value


def assign_partition(
    shape: tuple[int, int], *, pixel_size_m: float, block_size_m: float, halo_m: float, seed: str,
    development_fraction: float,
) -> np.ndarray:
    """Assign each cell to development, final holdout, or the excluded halo.

    Blocks are square ``block_size_m`` tiles anchored at the grid origin. A block
    is development when the first 8 bytes of ``sha256(seed:row:col)``, read as a
    fraction, fall below ``development_fraction``. Cells nearer than ``halo_m``
    to their block edge are excluded from both roles.
    """

    rows, cols = shape
    y = (np.arange(rows) + 0.5) * pixel_size_m
    x = (np.arange(cols) + 0.5) * pixel_size_m
    block_row, block_col = (y // block_size_m).astype(int), (x // block_size_m).astype(int)
    off_y, off_x = y - block_row * block_size_m, x - block_col * block_size_m
    inner_y = (off_y >= halo_m) & (off_y <= block_size_m - halo_m)
    inner_x = (off_x >= halo_m) & (off_x <= block_size_m - halo_m)
    role_by_block: dict[tuple[int, int], int] = {}
    for r in np.unique(block_row):
        for c in np.unique(block_col):
            digest = hashlib.sha256(f"{seed}:{int(r)}:{int(c)}".encode()).digest()
            draw = int.from_bytes(digest[:8], "big") / 2**64
            role_by_block[(int(r), int(c))] = PARTITION_DEVELOPMENT if draw < development_fraction else PARTITION_FINAL_HOLDOUT
    out = np.empty(shape, dtype=np.uint8)
    for i, r in enumerate(block_row):
        out[i] = [role_by_block[(int(r), int(c))] for c in block_col]
    out[~(inner_y[:, None] & inner_x[None, :])] = PARTITION_EXCLUDED
    return out


def compute_observation_metrics(
    reference_codes: np.ndarray, candidate: np.ndarray, mask: np.ndarray, *, pixel_size_m: float,
    boundary_tolerance_m: float,
) -> dict[str, Any]:
    """Score candidate flood/dry/abstain cells against reviewed reference codes inside ``mask``.

    Metrics whose denominator is zero are reported as ``None``, never as 0.
    """

    evaluable = mask & np.isin(reference_codes, (FloodLabel.DRY_LAND.value, FloodLabel.TEMPORARY_FLOOD.value))
    covered = evaluable & (candidate != CANDIDATE_ABSTAIN)
    ref_pos = reference_codes == FloodLabel.TEMPORARY_FLOOD.value
    pred_pos = candidate == CANDIDATE_FLOOD
    tp = int((covered & ref_pos & pred_pos).sum())
    fp = int((covered & ~ref_pos & pred_pos).sum())
    fn = int((covered & ref_pos & ~pred_pos).sum())
    tn = int((covered & ~ref_pos & ~pred_pos).sum())
    n_evaluable, n_covered = int(evaluable.sum()), int(covered.sum())
    ref_area = tp + fn
    pred_area = tp + fp
    boundary = None
    if n_covered:
        ref_grid = np.where(covered, reference_codes, FloodLabel.UNREVIEWED.value)
        cand_grid = np.where(covered, np.where(pred_pos, FloodLabel.TEMPORARY_FLOOD.value, FloodLabel.DRY_LAND.value), FloodLabel.UNREVIEWED.value)
        b = compute_boundary_f1(ref_grid.tolist(), cand_grid.tolist(), pixel_size_m=pixel_size_m, tolerance_m=boundary_tolerance_m)
        boundary = {"precision": b.precision, "recall": b.recall, "f1": b.f1, "tolerance_m": b.tolerance_m}
    return {
        "confusion": {"true_positive": tp, "false_positive": fp, "false_negative": fn, "true_negative": tn},
        "evaluable_cells": n_evaluable,
        "covered_cells": n_covered,
        "evaluated_coverage": _ratio(n_covered, n_evaluable),
        "iou": _ratio(tp, tp + fp + fn),
        "dice": _ratio(2 * tp, 2 * tp + fp + fn),
        "precision": _ratio(tp, tp + fp),
        "recall": _ratio(tp, tp + fn),
        "signed_area_error_fraction": _ratio(pred_area - ref_area, ref_area),
        "abs_area_error_fraction": None if ref_area == 0 else abs(pred_area - ref_area) / ref_area,
        "reference_flood_area_m2": ref_area * pixel_size_m**2,
        "candidate_flood_area_m2": pred_area * pixel_size_m**2,
        "boundary": boundary,
    }


def compare_to_limits(metrics: Mapping[str, Any], limits: Mapping[str, float]) -> dict[str, Any]:
    """Compare metrics with predeclared limits; an unavailable metric fails its limit."""

    observed = {
        "min_iou": metrics["iou"], "min_precision": metrics["precision"], "min_recall": metrics["recall"],
        "max_abs_area_error_fraction": metrics["abs_area_error_fraction"], "min_evaluated_coverage": metrics["evaluated_coverage"],
    }
    checks = {}
    for key in LIMIT_KEYS:
        value, limit = observed[key], limits[key]
        passed = value is not None and (value <= limit if key.startswith("max_") else value >= limit)
        checks[key] = {"observed": value, "limit": limit, "passed": bool(passed)}
    return {"checks": checks, "meets_predeclared_limits": all(c["passed"] for c in checks.values())}


def partition_sha256(partition: np.ndarray, role: int) -> str:
    """Hash the exact cell membership of one partition role."""

    return hashlib.sha256(np.ascontiguousarray(partition == role).tobytes()).hexdigest()


def evaluate_observation(
    plan: Mapping[str, Any],
    label_gate: Mapping[str, Any],
    reference_codes: np.ndarray,
    candidate: np.ndarray,
    *,
    role: str,
    strata: Mapping[str, np.ndarray] | None = None,
    holdout_opening: Mapping[str, Any] | None = None,
    source_timestamp: str,
) -> dict[str, Any]:
    """Run one gated evaluation and return a self-hashed result.

    ``label_gate`` must be the canonical qualified-release preflight result with
    ``eligible_for_real_experiment=True`` for the plan's label release. The
    ``final_holdout`` role additionally needs the verified custodian opening
    bound to this exact holdout membership and label release.
    """

    frozen = validate_evaluation_plan(plan, require_frozen=True)
    if role not in ROLES:
        raise ObservationEvaluationError(f"role must be one of {ROLES}")
    if label_gate.get("eligible_for_real_experiment") is not True:
        raise ObservationEvaluationError(
            "label release is not eligible for a real experiment "
            f"(status={label_gate.get('status')!r}); no metric is computed"
        )
    if label_gate.get("release_id") != frozen["reference"]["label_release_id"]:
        raise ObservationEvaluationError("label release differs from the one named by the frozen plan")
    reference_codes, candidate = np.asarray(reference_codes), np.asarray(candidate)
    if reference_codes.ndim != 2 or reference_codes.shape != candidate.shape:
        raise ObservationEvaluationError("reference and candidate must be 2D rasters of the same shape")
    allowed_ref = {label.value for label in FloodLabel}
    if not set(np.unique(reference_codes).tolist()) <= allowed_ref:
        raise ObservationEvaluationError("reference raster holds codes outside the flood label taxonomy")
    if not set(np.unique(candidate).tolist()) <= {CANDIDATE_DRY, CANDIDATE_FLOOD, CANDIDATE_ABSTAIN}:
        raise ObservationEvaluationError("candidate raster must hold only 0 dry, 1 flood or 255 abstain")

    p = frozen["partition"]
    partition = assign_partition(
        reference_codes.shape, pixel_size_m=frozen["pixel_size_m"], block_size_m=p["block_size_m"],
        halo_m=p["halo_m"], seed=p["seed"], development_fraction=p["development_fraction"],
    )
    role_code = PARTITION_DEVELOPMENT if role == "development" else PARTITION_FINAL_HOLDOUT
    holdout_hash = partition_sha256(partition, PARTITION_FINAL_HOLDOUT)
    opening_receipt_sha256 = None
    if role == "final_holdout":
        payload = (holdout_opening or {}).get("signed_payload") or {}
        if (holdout_opening or {}).get("status") != "signed_opening_verified_preflight_only":
            raise ObservationEvaluationError("final holdout needs a verified custodian opening")
        if payload.get("final_holdout_partition_sha256") != holdout_hash:
            raise ObservationEvaluationError("opening does not bind this exact final-holdout membership")
        if payload.get("qualified_release_set_sha256") != label_gate.get("qualified_label_release_sha256"):
            raise ObservationEvaluationError("opening does not bind this label release")
        opening_receipt_sha256 = holdout_opening["receipt_sha256"]

    mask = partition == role_code
    tol = frozen["boundary_tolerance_m"]
    overall = compute_observation_metrics(reference_codes, candidate, mask, pixel_size_m=frozen["pixel_size_m"], boundary_tolerance_m=tol)
    strata_out = {}
    for name in frozen["strata"]:
        stratum = (strata or {}).get(name)
        if stratum is None:
            strata_out[name] = None
            continue
        stratum = np.asarray(stratum, dtype=bool)
        if stratum.shape != mask.shape:
            raise ObservationEvaluationError(f"stratum {name} shape differs from the rasters")
        strata_out[name] = {
            "inside": compute_observation_metrics(reference_codes, candidate, mask & stratum, pixel_size_m=frozen["pixel_size_m"], boundary_tolerance_m=tol),
            "outside": compute_observation_metrics(reference_codes, candidate, mask & ~stratum, pixel_size_m=frozen["pixel_size_m"], boundary_tolerance_m=tol),
        }
    result = {
        "schema": RESULT_SCHEMA,
        "plan_id": frozen["plan_id"],
        "plan_sha256": canonical_sha256(frozen),
        "event_id": frozen["event_id"],
        "study_area_id": frozen["study_area_id"],
        "role": role,
        "label_release_id": label_gate["release_id"],
        "qualified_label_release_sha256": label_gate.get("qualified_label_release_sha256"),
        "final_holdout_partition_sha256": holdout_hash,
        "holdout_opening_receipt_sha256": opening_receipt_sha256,
        "metrics": overall,
        "strata": strata_out,
        "acceptance": compare_to_limits(overall, frozen["acceptance_limits"]),
        "evidence_tier": "bounded_single_event_observation_evaluation",
        "accepted_observation": False,
        "can_feed_decision_layer": False,
        "official_warning": False,
        "operational_status": "non_operational",
        "confidence": "agreement with one qualified single-event human reference under a frozen plan; no transfer to other events",
        "source_timestamp": source_timestamp,
        "processed_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "assumptions": ASSUMPTIONS,
    }
    result["result_sha256"] = canonical_sha256(result)
    return result


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def _positive(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def _non_negative(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0
