"""Frozen-plan, bounded single-event flood observation evaluation.

The original entry point scores a candidate flood-observation raster against a
qualified human reference raster, but only under a frozen, attributable evaluation plan
and a label release that the canonical release validator marks eligible for a
real experiment. It never loosens those gates: a draft plan, a fixture-only
label release, or an unverified final-holdout opening raises
``ObservationEvaluationError`` before any metric is computed.

A passing comparison against the plan's predeclared limits is still not an
accepted observation, FPPS input, or warning. Those need the separate
downstream acceptance receipt.

``evaluate_against_automated_reference`` is a separate, preregistered research
comparison. It reports agreement with an automated optical map, never accuracy
or human qualification, and cannot feed the decision layer.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


AUTOMATED_PREREG_SCHEMA = "floodguard.automated_preregistration.v1"
AUTOMATED_REFERENCE_SCHEMA = "floodguard.automated_optical_reference.v1"
AUTOMATED_RESULT_SCHEMA = "floodguard.automated_observation_evaluation_result.v1"
AUTOMATED_INTERPRETATION = "Agreement with an automated optical map, not accuracy."
AUTOMATED_PREREG_PATH = "docs/proposal_execution/automated_track/preregistration_v1.json"


def verify_automated_preregistration_commit(
    preregistration: Mapping[str, Any], commit_sha: str, repo_root: Path,
) -> str:
    """Verify that a Git commit contains the exact canonical pre-registration value."""

    plan = validate_automated_preregistration(preregistration)
    if not isinstance(commit_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
        raise ObservationEvaluationError("pre-registration commit SHA is invalid")
    try:
        shown = subprocess.run(
            ["git", "show", f"{commit_sha}:{AUTOMATED_PREREG_PATH}"], cwd=repo_root,
            check=True, capture_output=True,
        ).stdout
        committed = json.loads(shown.decode("utf-8"))
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError, ValueError) as error:
        raise ObservationEvaluationError("cannot verify the pre-registration Git commit") from error
    if canonical_sha256(committed) != canonical_sha256(plan):
        raise ObservationEvaluationError("pre-registration differs from committed Git content")
    return commit_sha


def validate_automated_preregistration(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the self-hashed, committed automated plan independently of the human plan."""

    value = dict(plan)
    digest = value.pop("preregistration_sha256", None)
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest) or digest != canonical_sha256(value):
        raise ObservationEvaluationError("automated pre-registration self-hash does not verify")
    if value.get("schema") != AUTOMATED_PREREG_SCHEMA or value.get("status") != "preregistered":
        raise ObservationEvaluationError("automated pre-registration schema or status is invalid")
    if value.get("preregistered_by") != "automated agent (Codex)":
        raise ObservationEvaluationError("automated pre-registration actor is invalid")
    if value.get("roles_in_order") != ["development", "final_holdout"]:
        raise ObservationEvaluationError("automated evaluation roles are not frozen in order")
    if value.get("human_reviewed") is not False or value.get("official_warning") is not False:
        raise ObservationEvaluationError("automated pre-registration has unsafe human or warning flags")
    if value.get("can_feed_decision_layer") is not False or value.get("operational_status") != "non_operational":
        raise ObservationEvaluationError("automated pre-registration has unsafe decision flags")
    if value.get("metric_interpretation") != AUTOMATED_INTERPRETATION:
        raise ObservationEvaluationError("automated metric interpretation is missing")
    if value.get("candidate_alignment") != {
        "resampling": "nearest", "outside_footprint_or_nodata": 255, "allowed_codes": [0, 1, 255],
    }:
        raise ObservationEvaluationError("candidate alignment differs from the frozen rule")
    partition = value.get("partition")
    if not isinstance(partition, dict) or set(partition) != {"block_size_m", "halo_m", "seed", "development_fraction"}:
        raise ObservationEvaluationError("automated partition is invalid")
    if not (_positive(partition["block_size_m"]) and _non_negative(partition["halo_m"])
            and 2 * partition["halo_m"] < partition["block_size_m"]
            and _positive(partition["development_fraction"]) and partition["development_fraction"] < 1
            and isinstance(partition["seed"], str) and partition["seed"]):
        raise ObservationEvaluationError("automated partition parameters are invalid")
    if not _positive(value.get("grid", {}).get("pixel_size_m")) or not _non_negative(value.get("boundary_tolerance_m")):
        raise ObservationEvaluationError("automated grid or boundary tolerance is invalid")
    limits = value.get("acceptance_limits")
    if not isinstance(limits, dict) or set(limits) != set(LIMIT_KEYS) or any(
        not isinstance(x, (int, float)) or isinstance(x, bool) or not math.isfinite(x) or not 0 <= x <= 1
        for x in limits.values()
    ):
        raise ObservationEvaluationError("automated acceptance limits are invalid")
    candidates = value.get("candidate_products")
    if not isinstance(candidates, list) or len(candidates) != 2:
        raise ObservationEvaluationError("exactly two predeclared candidates are required")
    ids = [candidate.get("product_id") for candidate in candidates if isinstance(candidate, dict)]
    if len(ids) != 2 or len(set(ids)) != 2 or any(not isinstance(identifier, str) or not identifier for identifier in ids):
        raise ObservationEvaluationError("automated candidate IDs are invalid")
    for candidate in candidates:
        for key in ("raster_sha256", "source_receipt_sha256"):
            if not isinstance(candidate.get(key), str) or not _SHA256.fullmatch(candidate[key]):
                raise ObservationEvaluationError(f"candidate {candidate['product_id']} has invalid {key}")
    return dict(plan)


def validate_automated_evaluation_result(
    result: Mapping[str, Any], preregistration: Mapping[str, Any], reference_receipt: Mapping[str, Any],
    *, development_result: Path | None = None, holdout_marker: Path | None = None,
) -> dict[str, Any]:
    """Verify a result and, for final holdout, its actual development and ledger files."""

    plan = validate_automated_preregistration(preregistration)
    reference = _validate_automated_reference_binding(reference_receipt, plan, result.get("preregistration_commit_sha"))
    verify_automated_preregistration_commit(
        plan, result["preregistration_commit_sha"], Path(__file__).resolve().parents[2],
    )
    value = dict(result)
    digest = value.pop("result_sha256", None)
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest) or digest != canonical_sha256(value):
        raise ObservationEvaluationError("automated evaluation result self-hash does not verify")
    if value.get("schema") != AUTOMATED_RESULT_SCHEMA or value.get("role") not in ROLES:
        raise ObservationEvaluationError("automated evaluation result schema or role is invalid")
    if value.get("preregistration_sha256") != plan["preregistration_sha256"]:
        raise ObservationEvaluationError("automated result uses another pre-registration")
    if value.get("automated_reference_receipt_sha256") != reference["receipt_sha256"]:
        raise ObservationEvaluationError("automated result uses another optical reference")
    if value.get("reference_raster_sha256") != reference.get("label_raster_sha256"):
        raise ObservationEvaluationError("automated result uses another reference raster")
    if (value.get("plan_id"), value.get("event_id"), value.get("study_area_id")) != (
        plan["plan_id"], plan["event_id"], plan["study_area_id"],
    ):
        raise ObservationEvaluationError("automated result uses another event or plan")
    if value.get("metric_interpretation") != AUTOMATED_INTERPRETATION:
        raise ObservationEvaluationError("automated result interpretation is missing")
    if not isinstance(value.get("source_timestamp"), str) or not value["source_timestamp"]:
        raise ObservationEvaluationError("automated result source timestamp is missing")
    if not isinstance(value.get("confidence"), str) or not value["confidence"]:
        raise ObservationEvaluationError("automated result confidence is missing")
    if not isinstance(value.get("assumptions"), list) or not value["assumptions"]:
        raise ObservationEvaluationError("automated result assumptions are missing")
    required_flags = {
        "evidence_tier": "preregistered_automated_evaluation",
        "reference_kind": "automated_optical_reference",
        "human_reviewed": False,
        "accepted_observation": False,
        "can_feed_decision_layer": False,
        "official_warning": False,
        "operational_status": "non_operational",
    }
    if any(value.get(key) != expected or type(value.get(key)) is not type(expected) for key, expected in required_flags.items()):
        raise ObservationEvaluationError("automated result safety fields are invalid")
    expected_candidates = {candidate["product_id"]: candidate for candidate in plan["candidate_products"]}
    results = value.get("candidate_results")
    if not isinstance(results, dict) or set(results) != set(expected_candidates):
        raise ObservationEvaluationError("automated result must contain both predeclared candidates")
    for identifier, declared in expected_candidates.items():
        candidate = results[identifier]
        if not isinstance(candidate, dict) or candidate.get("processing_variant") != declared["processing_variant"]:
            raise ObservationEvaluationError(f"candidate {identifier} processing variant differs from pre-registration")
        if candidate.get("source_raster_sha256") != declared["raster_sha256"] or candidate.get("source_receipt_sha256") != declared["source_receipt_sha256"]:
            raise ObservationEvaluationError(f"candidate {identifier} source hashes differ from pre-registration")
        if not isinstance(candidate.get("aligned_cells_sha256"), str) or not _SHA256.fullmatch(candidate["aligned_cells_sha256"]):
            raise ObservationEvaluationError(f"candidate {identifier} aligned-cell hash is invalid")
        if not isinstance(candidate.get("source_timestamp"), str) or not candidate["source_timestamp"]:
            raise ObservationEvaluationError(f"candidate {identifier} source timestamp is missing")
        if candidate.get("possible_recession_candidate_cells") != candidate.get("metrics", {}).get("confusion", {}).get("false_negative"):
            raise ObservationEvaluationError(f"candidate {identifier} recession diagnostic differs from false negatives")
        if candidate.get("acceptance") != compare_to_limits(candidate["metrics"], plan["acceptance_limits"]):
            raise ObservationEvaluationError(f"candidate {identifier} acceptance differs from predeclared limits")
    if not isinstance(value.get("final_holdout_partition_sha256"), str) or not _SHA256.fullmatch(value["final_holdout_partition_sha256"]):
        raise ObservationEvaluationError("automated result partition hash is invalid")
    if value["role"] == "final_holdout":
        _validate_automated_final_evidence(
            value, plan, reference, development_result=development_result, holdout_marker=holdout_marker,
        )
    if value["role"] == "development" and value.get("automated_holdout_consumption_sha256") is not None:
        raise ObservationEvaluationError("development result has a final-holdout consumption")
    if value["role"] == "development" and value.get("development_result_sha256") is not None:
        raise ObservationEvaluationError("development result cannot bind a predecessor")
    return dict(result)


def _validate_automated_final_evidence(
    final: Mapping[str, Any], plan: Mapping[str, Any], reference: Mapping[str, Any],
    *, development_result: Path | None, holdout_marker: Path | None,
) -> None:
    """Bind a final result to the existing one-use marker and development file."""

    if development_result is None or holdout_marker is None:
        raise ObservationEvaluationError("final automated result requires development result and holdout marker files")
    development_path = Path(development_result)
    marker_path = Path(holdout_marker)
    if not development_path.is_file() or development_path.is_symlink():
        raise ObservationEvaluationError("automated development result file is missing or a symlink")
    if not marker_path.is_file() or _automated_has_symlink_component(marker_path):
        raise ObservationEvaluationError("automated holdout marker is missing or has a symlink component")
    if marker_path.resolve().is_relative_to(Path(__file__).resolve().parents[2]):
        raise ObservationEvaluationError("automated holdout marker must be outside Git")
    if marker_path.name != f"automated_holdout_consumption-{final['final_holdout_partition_sha256']}.json":
        raise ObservationEvaluationError("automated holdout marker filename differs from partition")
    try:
        development_value = json.loads(development_path.read_text(encoding="utf-8"))
        marker_bytes = marker_path.read_bytes()
        marker = json.loads(marker_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise ObservationEvaluationError("cannot read automated development result or holdout marker") from error
    if not isinstance(development_value, dict) or not isinstance(marker, dict):
        raise ObservationEvaluationError("automated development result or holdout marker is not a JSON object")
    development = validate_automated_evaluation_result(development_value, plan, reference)
    if development["role"] != "development" or development["result_sha256"] != final.get("development_result_sha256"):
        raise ObservationEvaluationError("final automated result differs from its development result")
    if development["final_holdout_partition_sha256"] != final["final_holdout_partition_sha256"]:
        raise ObservationEvaluationError("final automated partition differs from development")
    for identifier, final_candidate in final["candidate_results"].items():
        development_candidate = development["candidate_results"][identifier]
        if final_candidate["aligned_cells_sha256"] != development_candidate["aligned_cells_sha256"]:
            raise ObservationEvaluationError(f"final candidate {identifier} differs from development aligned cells")
    expected_marker = {
        "schema": "floodguard.automated_holdout_consumption.v1",
        "status": "local_exclusive_consumption",
        "final_holdout_partition_sha256": final["final_holdout_partition_sha256"],
        "preregistration_sha256": plan["preregistration_sha256"],
        "preregistration_commit_sha": final["preregistration_commit_sha"],
        "automated_reference_receipt_sha256": reference["receipt_sha256"],
        "development_result_sha256": development["result_sha256"],
    }
    if set(marker) != {*expected_marker, "consumed_at_utc"} or any(
        marker.get(key) != expected for key, expected in expected_marker.items()
    ):
        raise ObservationEvaluationError("automated holdout marker bindings are invalid")
    consumed_at = marker.get("consumed_at_utc")
    if not isinstance(consumed_at, str) or not _UTC.fullmatch(consumed_at):
        raise ObservationEvaluationError("automated holdout marker timestamp is invalid")
    try:
        datetime.fromisoformat(consumed_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ObservationEvaluationError("automated holdout marker timestamp is invalid") from error
    serialized = json.dumps(marker, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"
    if marker_bytes != serialized:
        raise ObservationEvaluationError("automated holdout marker bytes are not canonical")
    if canonical_sha256(marker) != final.get("automated_holdout_consumption_sha256"):
        raise ObservationEvaluationError("automated holdout marker hash differs from final result")


def evaluate_against_automated_reference(
    preregistration: Mapping[str, Any],
    reference_receipt: Mapping[str, Any],
    reference_codes: np.ndarray,
    candidate_rasters: Mapping[str, np.ndarray],
    candidate_sources: Mapping[str, Mapping[str, Any]],
    *,
    role: str,
    preregistration_commit_sha: str,
    reference_raster_sha256: str,
    development_result: Mapping[str, Any] | None = None,
    external_ledger_dir: Path | None = None,
) -> dict[str, Any]:
    """Evaluate both frozen SAR candidates against one automated optical map.

    Final holdout requires a validated development result and consumes one
    exclusive marker before either final comparison is computed. A failed run
    after that point remains consumed and must be reported as such.
    """

    plan = validate_automated_preregistration(preregistration)
    reference = _validate_automated_reference_binding(reference_receipt, plan, preregistration_commit_sha)
    verify_automated_preregistration_commit(
        plan, preregistration_commit_sha, Path(__file__).resolve().parents[2],
    )
    if reference_raster_sha256 != reference.get("label_raster_sha256"):
        raise ObservationEvaluationError("automated reference raster hash differs from receipt")
    if role not in ROLES:
        raise ObservationEvaluationError(f"automated role must be one of {ROLES}")
    expected = {candidate["product_id"]: candidate for candidate in plan["candidate_products"]}
    if set(candidate_rasters) != set(expected) or set(candidate_sources) != set(expected):
        raise ObservationEvaluationError("both predeclared candidates must be evaluated together")
    ref = np.asarray(reference_codes)
    if ref.ndim != 2 or ref.dtype.kind not in "ui" or not set(np.unique(ref).tolist()) <= {0, 1, 2, 3, 4, 255}:
        raise ObservationEvaluationError("automated reference raster codes are invalid")
    aligned: dict[str, np.ndarray] = {}
    for identifier, declared in expected.items():
        source = candidate_sources[identifier]
        if source.get("source_raster_sha256") != declared["raster_sha256"] or source.get("source_receipt_sha256") != declared["source_receipt_sha256"]:
            raise ObservationEvaluationError(f"candidate {identifier} source hashes differ from pre-registration")
        candidate = np.asarray(candidate_rasters[identifier])
        if candidate.ndim != 2 or candidate.shape != ref.shape or candidate.dtype.kind not in "ui":
            raise ObservationEvaluationError(f"candidate {identifier} is not an aligned 2D integer raster")
        if not set(np.unique(candidate).tolist()) <= {0, 1, 255}:
            raise ObservationEvaluationError(f"candidate {identifier} contains codes outside 0, 1, 255")
        if not isinstance(source.get("source_timestamp"), str) or not source["source_timestamp"]:
            raise ObservationEvaluationError(f"candidate {identifier} source timestamp is missing")
        grid = source.get("source_grid")
        bounds = source.get("source_bounds")
        native = declared["native_pixel_size_m"]
        if (
            not isinstance(grid, dict) or grid.get("crs") != plan["grid"]["crs"]
            or not isinstance(grid.get("width"), int) or grid["width"] <= 0
            or not isinstance(grid.get("height"), int) or grid["height"] <= 0
            or not isinstance(grid.get("transform"), list) or len(grid["transform"]) != 6
            or grid["transform"][0] != native or grid["transform"][4] != -native
            or grid["transform"][1] != 0 or grid["transform"][3] != 0
            or grid.get("nodata") != 255
        ):
            raise ObservationEvaluationError(f"candidate {identifier} source grid differs from pre-registration")
        if not isinstance(bounds, list) or len(bounds) != 4 or any(
            not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value)
            for value in bounds
        ) or bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
            raise ObservationEvaluationError(f"candidate {identifier} source bounds are invalid")
        aligned[identifier] = candidate
    partition_rule = plan["partition"]
    partition = assign_partition(
        ref.shape, pixel_size_m=plan["grid"]["pixel_size_m"], block_size_m=partition_rule["block_size_m"],
        halo_m=partition_rule["halo_m"], seed=partition_rule["seed"],
        development_fraction=partition_rule["development_fraction"],
    )
    holdout_hash = partition_sha256(partition, PARTITION_FINAL_HOLDOUT)
    consumption_sha256 = None
    development_hash = None
    if role == "final_holdout":
        if development_result is None:
            raise ObservationEvaluationError("final holdout requires the prior development result")
        development = validate_automated_evaluation_result(development_result, plan, reference)
        if development["role"] != "development" or development["final_holdout_partition_sha256"] != holdout_hash:
            raise ObservationEvaluationError("development result does not bind this holdout partition")
        for identifier in expected:
            if development["candidate_results"][identifier]["source_raster_sha256"] != candidate_sources[identifier]["source_raster_sha256"]:
                raise ObservationEvaluationError("final candidate differs from development candidate")
            current_aligned_hash = hashlib.sha256(np.ascontiguousarray(aligned[identifier], dtype=np.uint8).tobytes()).hexdigest()
            if development["candidate_results"][identifier]["aligned_cells_sha256"] != current_aligned_hash:
                raise ObservationEvaluationError("final aligned candidate differs from development candidate")
        if external_ledger_dir is None:
            raise ObservationEvaluationError("final holdout requires an external consumption ledger")
        development_hash = development["result_sha256"]
        consumption = _consume_automated_holdout(
            Path(external_ledger_dir), holdout_hash=holdout_hash, plan_hash=plan["preregistration_sha256"],
            commit_sha=preregistration_commit_sha, reference_hash=reference["receipt_sha256"],
            development_hash=development_hash,
        )
        consumption_sha256 = canonical_sha256(consumption)
    mask = partition == (PARTITION_DEVELOPMENT if role == "development" else PARTITION_FINAL_HOLDOUT)
    results: dict[str, Any] = {}
    for identifier, declared in expected.items():
        candidate = aligned[identifier]
        metrics = compute_observation_metrics(
            ref, candidate, mask, pixel_size_m=plan["grid"]["pixel_size_m"],
            boundary_tolerance_m=plan["boundary_tolerance_m"],
        )
        source = candidate_sources[identifier]
        results[identifier] = {
            "processing_variant": declared["processing_variant"],
            "source_raster_sha256": source["source_raster_sha256"],
            "source_receipt_sha256": source["source_receipt_sha256"],
            "source_grid": source["source_grid"],
            "source_bounds": source["source_bounds"],
            "source_timestamp": source["source_timestamp"],
            "aligned_cells_sha256": hashlib.sha256(np.ascontiguousarray(candidate, dtype=np.uint8).tobytes()).hexdigest(),
            "metrics": metrics,
            "acceptance": compare_to_limits(metrics, plan["acceptance_limits"]),
            "possible_recession_candidate_cells": int((mask & (ref == 1) & (candidate == 0)).sum()),
        }
    result = {
        "schema": AUTOMATED_RESULT_SCHEMA,
        "plan_id": plan["plan_id"],
        "event_id": plan["event_id"],
        "study_area_id": plan["study_area_id"],
        "role": role,
        "preregistration_sha256": plan["preregistration_sha256"],
        "preregistration_commit_sha": preregistration_commit_sha,
        "automated_reference_receipt_sha256": reference["receipt_sha256"],
        "reference_raster_sha256": reference_raster_sha256,
        "final_holdout_partition_sha256": holdout_hash,
        "automated_holdout_consumption_sha256": consumption_sha256,
        "development_result_sha256": development_hash,
        "candidate_results": results,
        "metric_interpretation": AUTOMATED_INTERPRETATION,
        "evidence_tier": "preregistered_automated_evaluation",
        "reference_kind": "automated_optical_reference",
        "human_reviewed": False,
        "accepted_observation": False,
        "can_feed_decision_layer": False,
        "official_warning": False,
        "operational_status": "non_operational",
        "confidence": "Single-event agreement with an automated optical map; 19h31m sensor timing gap and spectral limits apply.",
        "source_timestamp": plan["source"]["event_sensing_utc"],
        "processed_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "assumptions": [
            "Only reference codes 0 and 1 are scored; codes 2, 3, 4 and 255 remain excluded.",
            "Out-of-footprint and source nodata candidate cells remain code 255 abstentions.",
            "Possible recession is a time-gap diagnostic, not an established cause of disagreement.",
            "Meeting limits does not authorize an accepted observation, FPPS component or warning.",
        ],
    }
    result["result_sha256"] = canonical_sha256(result)
    return result


def _validate_automated_reference_binding(
    reference_receipt: Mapping[str, Any], plan: Mapping[str, Any], commit_sha: Any,
) -> dict[str, Any]:
    if not isinstance(commit_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
        raise ObservationEvaluationError("pre-registration commit SHA is invalid")
    receipt = dict(reference_receipt)
    digest = receipt.pop("receipt_sha256", None)
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest) or digest != canonical_sha256(receipt):
        raise ObservationEvaluationError("automated reference receipt self-hash does not verify")
    if receipt.get("schema") != AUTOMATED_REFERENCE_SCHEMA:
        raise ObservationEvaluationError("automated reference receipt schema is invalid")
    if receipt.get("preregistration_sha256") != plan["preregistration_sha256"] or receipt.get("preregistration_commit") != commit_sha:
        raise ObservationEvaluationError("automated reference differs from pre-registration commit or hash")
    if receipt.get("human_reviewed") is not False or receipt.get("official_warning") is not False:
        raise ObservationEvaluationError("automated reference has unsafe review or warning flags")
    return dict(reference_receipt)


def _consume_automated_holdout(
    ledger_dir: Path, *, holdout_hash: str, plan_hash: str, commit_sha: str,
    reference_hash: str, development_hash: str,
) -> dict[str, Any]:
    if _automated_has_symlink_component(ledger_dir) or not ledger_dir.is_dir():
        raise ObservationEvaluationError("automated holdout ledger must exist without symlinks")
    if ledger_dir.resolve().is_relative_to(Path(__file__).resolve().parents[2]):
        raise ObservationEvaluationError("automated holdout ledger must be outside Git")
    marker = ledger_dir / f"automated_holdout_consumption-{holdout_hash}.json"
    receipt = {
        "schema": "floodguard.automated_holdout_consumption.v1",
        "status": "local_exclusive_consumption",
        "final_holdout_partition_sha256": holdout_hash,
        "preregistration_sha256": plan_hash,
        "preregistration_commit_sha": commit_sha,
        "automated_reference_receipt_sha256": reference_hash,
        "development_result_sha256": development_hash,
        "consumed_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    try:
        with marker.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(receipt, stream, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise ObservationEvaluationError("automated final holdout has already been consumed") from error
    except OSError as error:
        raise ObservationEvaluationError(f"cannot record automated holdout consumption: {error}") from error
    return receipt


def _automated_has_symlink_component(path: Path) -> bool:
    current = path
    while True:
        if current.is_symlink():
            return True
        if current.parent == current:
            return False
        current = current.parent
