"""Fail-closed audit of synthetic Reviewer A practice exports.

This module intentionally operates only on the conceptual synthetic learning
package and the browser workbench's practice schemas.  Its outputs are learning
diagnostics.  They are never formal reviewer calibration, agreement evidence,
training labels, model-evaluation evidence, decision-layer inputs, FPPS inputs,
or warning inputs.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Mapping, Sequence

from floodguard.label_factory.reviewer_workspace import (
    ReviewerWorkspaceError,
    _read_label_codes,
)
from floodguard.label_factory.synthetic_learning import (
    SYNTHETIC_LEARNING_SCHEMA,
    SyntheticLearningError,
    verify_synthetic_learning_package,
)
from floodguard.label_factory.synthetic_remediation import (
    CASE_IDS as REMEDIATION_CASE_IDS,
    SYNTHETIC_REMEDIATION_SCHEMA,
    SyntheticRemediationError,
    verify_synthetic_remediation_package,
)


AUDIT_SCHEMA = "floodguard.reviewer_practice_audit.v1"
INPUT_HASH_SCHEMA = "floodguard.reviewer_practice_audit_inputs.v1"
SESSION_SCHEMA = "floodguard.reviewer_practice_export.v1"
DRAFT_SCHEMA = "floodguard.reviewer_practice_draft.v1"
WORKSPACE_ID_PATTERN = re.compile(r"FG-PRACTICE-[0-9A-F]{16}")
UTC_TIMESTAMP_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")

LABEL_NAMES: Mapping[int, str] = {
    0: "dry_land",
    1: "temporary_flood",
    2: "permanent_or_preexisting_water",
    3: "uncertain_water_change",
    4: "unobservable_or_artifact",
    255: "unreviewed",
}
REVIEWED_CODES = (0, 1, 2, 3, 4)
ALL_CODES = (*REVIEWED_CODES, 255)
PRIMARY_ASSESSMENTS = (
    "dry_land",
    "temporary_flood",
    "permanent_or_preexisting_water",
    "uncertain_water_change",
    "unobservable_or_artifact",
    "mixed_geometry",
)
CONFIDENCE_VALUES = ("high", "medium", "low")
AMBIGUITY_VALUES = (
    "urban_double_bounce",
    "urban_layover",
    "radar_shadow",
    "steep_terrain",
    "wet_soil_or_agricultural_change",
    "flooded_vegetation",
    "permanent_water_boundary",
    "speckle_or_isolated_response",
    "pre_post_misregistration",
    "temporal_mismatch",
    "other",
)
EVIDENCE_LAYERS = (
    "pre_vv",
    "event_vv",
    "pre_vh",
    "event_vh",
    "vv_change",
    "permanent_water",
    "slope",
    "landcover",
)
EXPECTED_PRIMARY = {
    "0 dry": "dry_land",
    "1 temporary_flood": "temporary_flood",
    "2 permanent_water": "permanent_or_preexisting_water",
    "3 uncertain": "uncertain_water_change",
    "4 unobservable": "unobservable_or_artifact",
    "mixed_geometry": "mixed_geometry",
}
SAFETY_FLAGS: Mapping[str, bool] = {
    "practice_only": True,
    "conceptual_teaching_only": True,
    "formal_review_authorized": False,
    "formal_reviewer_calibration": False,
    "real_event_queries_used": False,
    "eligible_for_reviewer_calibration": False,
    "eligible_for_agreement": False,
    "eligible_for_consensus": False,
    "eligible_for_query_model_training": False,
    "eligible_for_model_evaluation": False,
    "eligible_for_decision_layer": False,
    "eligible_for_fpps": False,
    "eligible_for_warning": False,
}

SESSION_KEYS = {
    "artifact_schema",
    "workspace_id",
    "reviewer_display_name",
    "exported_at_utc",
    *SAFETY_FLAGS,
    "cases",
}
SESSION_CASE_KEYS = {
    "practice_case_id",
    "locked",
    "started_at_utc",
    "locked_at_utc",
    "duration_seconds",
    "primary_assessment",
    "confidence",
    "ambiguity_reason_codes",
    "evidence_layers_viewed",
    "notes",
    "practice_cell_codes",
    "post_lock_feedback_revealed",
    "practice_score",
}
DRAFT_KEYS = {
    "artifact_schema",
    "workspace_id",
    "reviewer_display_name",
    "saved_at_utc",
    "case_index",
    "attempts",
}
DRAFT_ATTEMPT_KEYS = {
    "labels",
    "history",
    "future",
    "locked",
    "revealed",
    "started_at_utc",
    "locked_at_utc",
    "duration_seconds",
    "confidence",
    "primaryAssessment",
    "ambiguity",
    "notes",
    "visitedLayers",
    "score",
}
SCORE_KEYS = {
    "accuracy",
    "temporary_flood_dice",
    "correct_cells",
    "true_positive",
    "false_positive",
    "false_negative",
}
CSV_COLUMNS = (
    "practice_workspace_id",
    "practice_case_id",
    "reviewer_display_name",
    "locked_at_utc",
    "duration_seconds",
    "confidence",
    "row_index",
    "column_index",
    "practice_label_code",
    "practice_label_name",
    "post_lock_feedback_revealed",
)
CASE_METRIC_COLUMNS = (
    "practice_case_id",
    "teaching_challenge",
    "selected_primary_assessment",
    "expected_primary_assessment",
    "primary_assessment_matches",
    "confidence",
    "started_at_utc",
    "locked_at_utc",
    "duration_seconds",
    "accuracy",
    "temporary_flood_dice",
    "correct_cells",
    "true_positive",
    "false_positive",
    "false_negative",
    "truth_temporary_flood_cells",
    "predicted_temporary_flood_cells",
    "evidence_layer_count",
    "all_evidence_layers_viewed",
    "missing_evidence_layers",
    "reasoning_note_present",
    "ambiguity_reason_codes",
)
CONFUSION_COLUMNS = (
    "truth_label_code",
    "truth_label_name",
    "predicted_label_code",
    "predicted_label_name",
    "cell_count",
)

PRACTICE_THRESHOLDS: Mapping[str, float | int] = {
    "minimum_aggregate_temporary_flood_dice": 0.75,
    "minimum_mean_flood_present_case_dice": 0.75,
    "minimum_primary_assessment_match_rate": 0.80,
    "required_reasoning_note_completion_rate": 1.0,
    "required_all_layer_inspection_rate": 1.0,
    "maximum_zero_dice_flood_present_cases": 0,
}

SYNTHETIC_PROFILES: Mapping[str, Mapping[str, Any]] = {
    SYNTHETIC_LEARNING_SCHEMA: {
        "stage": "first_pass",
        "case_ids": tuple(f"SYN-SAR-{index:03d}" for index in range(1, 21)),
        "verify": verify_synthetic_learning_package,
    },
    SYNTHETIC_REMEDIATION_SCHEMA: {
        "stage": "targeted_remediation",
        "case_ids": REMEDIATION_CASE_IDS,
        "verify": verify_synthetic_remediation_package,
    },
}


class PracticeAuditError(ValueError):
    """Raised when a practice export cannot be trusted or safely audited."""


def audit_reviewer_practice_exports(
    session_json: str | Path,
    draft_json: str | Path,
    cells_csv: str | Path,
    synthetic_package: str | Path,
    output_directory: str | Path,
    *,
    audited_at_utc: datetime,
) -> Path:
    """Validate practice exports and write a self-hashed learning audit.

    Every input-integrity rule is fail-closed.  A successful return means the
    three exports agree exactly with one another and their scores can be
    reproduced from the checksum-verified synthetic teaching answers.  It does
    not mean that a reviewer passed formal calibration.
    """

    inputs = {
        "session_json": Path(session_json).resolve(),
        "draft_json": Path(draft_json).resolve(),
        "cells_csv": Path(cells_csv).resolve(),
    }
    synthetic_root = Path(synthetic_package).resolve()
    target = Path(output_directory).resolve()
    audited_at = _utc_timestamp(audited_at_utc, "audited_at_utc")
    _validate_input_and_output_locations(inputs, synthetic_root, target)

    initial_hashes = {name: _sha256(path) for name, path in inputs.items()}
    synthetic_manifest_path = synthetic_root / "manifest.json"
    initial_synthetic_manifest_hash = _sha256(synthetic_manifest_path)
    synthetic_manifest = _read_json_object(
        synthetic_manifest_path, "synthetic manifest"
    )
    profile = _synthetic_profile(synthetic_manifest)
    verifier = profile["verify"]
    assert callable(verifier)
    try:
        verifier(synthetic_root)
    except (
        SyntheticLearningError,
        SyntheticRemediationError,
        OSError,
        ValueError,
    ) as exc:
        raise PracticeAuditError(
            f"Synthetic practice package verification failed: {exc}"
        ) from exc
    session = _read_json_object(inputs["session_json"], "practice session")
    draft = _read_json_object(inputs["draft_json"], "practice draft")
    _require_exact_keys(session, SESSION_KEYS, "practice session")
    _require_exact_keys(draft, DRAFT_KEYS, "practice draft")
    _validate_schemas_and_identity(session, draft)
    exported_at = _parse_utc(session["exported_at_utc"], "exported_at_utc")
    saved_at = _parse_utc(draft["saved_at_utc"], "saved_at_utc")
    audit_time = _parse_utc(audited_at, "audited_at_utc")
    if exported_at > audit_time or saved_at > audit_time:
        raise PracticeAuditError("Practice export timestamps cannot be after the audit time.")

    cases = _synthetic_cases(synthetic_manifest, synthetic_root, profile)
    case_ids = [row["case_id"] for row in cases]
    session_cases = _session_cases(session, case_ids)
    draft_attempts = _draft_attempts(draft, case_ids)
    csv_cells = _read_and_validate_cells_csv(
        inputs["cells_csv"], session, session_cases, case_ids
    )

    case_metrics: list[dict[str, Any]] = []
    confusion: dict[tuple[int, int], int] = {
        (truth, predicted): 0
        for truth in REVIEWED_CODES
        for predicted in REVIEWED_CODES
    }
    intervals: list[tuple[datetime, datetime, str]] = []
    total_active_seconds = 0.0
    for case in cases:
        case_id = case["case_id"]
        session_case = session_cases[case_id]
        draft_attempt = draft_attempts[case_id]
        answer_codes = case["answer_codes"]
        selected_codes = _validate_case_and_draft(
            session_case,
            draft_attempt,
            csv_cells[case_id],
            answer_codes,
            case_id,
        )
        started_at = _parse_utc(
            session_case["started_at_utc"], f"{case_id} started_at_utc"
        )
        locked_at = _parse_utc(
            session_case["locked_at_utc"], f"{case_id} locked_at_utc"
        )
        duration = _finite_number(
            session_case["duration_seconds"], f"{case_id} duration_seconds"
        )
        if duration < 0 or locked_at < started_at:
            raise PracticeAuditError(f"{case_id} has invalid review timing.")
        if duration > (locked_at - started_at).total_seconds() + 2.0:
            raise PracticeAuditError(
                f"{case_id} active duration exceeds its wall-clock interval."
            )
        if locked_at > exported_at or locked_at > saved_at:
            raise PracticeAuditError(
                f"{case_id} was locked after a supplied export timestamp."
            )
        intervals.append((started_at, locked_at, case_id))
        total_active_seconds += duration

        score = _score(selected_codes, answer_codes)
        _require_score(session_case["practice_score"], score, f"{case_id} session")
        _require_score(draft_attempt["score"], score, f"{case_id} draft")
        for truth, predicted in zip(answer_codes, selected_codes, strict=True):
            confusion[(truth, predicted)] += 1

        selected_primary = session_case["primary_assessment"]
        expected_primary = case["expected_primary"]
        viewed_layers = session_case["evidence_layers_viewed"]
        missing_layers = [
            layer for layer in EVIDENCE_LAYERS if layer not in viewed_layers
        ]
        case_metrics.append(
            {
                "practice_case_id": case_id,
                "teaching_challenge": case["challenge"],
                "selected_primary_assessment": selected_primary,
                "expected_primary_assessment": expected_primary,
                "primary_assessment_matches": selected_primary == expected_primary,
                "confidence": session_case["confidence"],
                "started_at_utc": session_case["started_at_utc"],
                "locked_at_utc": session_case["locked_at_utc"],
                "duration_seconds": duration,
                **score,
                "truth_temporary_flood_cells": (
                    score["true_positive"] + score["false_negative"]
                ),
                "predicted_temporary_flood_cells": (
                    score["true_positive"] + score["false_positive"]
                ),
                "evidence_layer_count": len(viewed_layers),
                "all_evidence_layers_viewed": not missing_layers,
                "missing_evidence_layers": missing_layers,
                "reasoning_note_present": bool(session_case["notes"].strip()),
                "ambiguity_reason_codes": list(
                    session_case["ambiguity_reason_codes"]
                ),
            }
        )

    _require_non_overlapping_intervals(intervals)
    summary_metrics, heuristics, next_step_status = _practice_summary(
        case_metrics,
        confusion,
        total_active_seconds,
        practice_stage=str(profile["stage"]),
    )

    final_hashes = {name: _sha256(path) for name, path in inputs.items()}
    if final_hashes != initial_hashes:
        raise PracticeAuditError("A practice export changed during the audit.")
    if _sha256(synthetic_manifest_path) != initial_synthetic_manifest_hash:
        raise PracticeAuditError("The synthetic manifest changed during the audit.")

    input_hashes = {
        **initial_hashes,
        "synthetic_manifest_file": initial_synthetic_manifest_hash,
        "synthetic_manifest_self": _required_sha256(
            synthetic_manifest.get("manifest_sha256"),
            "synthetic manifest self hash",
        ),
    }
    return _write_audit_outputs(
        target,
        audited_at=audited_at,
        workspace_id=session["workspace_id"],
        reviewer_display_name=session["reviewer_display_name"],
        exported_at=session["exported_at_utc"],
        saved_at=draft["saved_at_utc"],
        input_hashes=input_hashes,
        case_metrics=case_metrics,
        confusion=confusion,
        summary_metrics=summary_metrics,
        heuristics=heuristics,
        next_step_status=next_step_status,
        source_package_schema=str(synthetic_manifest["artifact_schema"]),
        practice_stage=str(profile["stage"]),
    )


def _validate_input_and_output_locations(
    inputs: Mapping[str, Path], synthetic_root: Path, target: Path
) -> None:
    for name, path in inputs.items():
        if not path.is_file():
            raise PracticeAuditError(f"{name} does not exist: {path}")
    manifest = synthetic_root / "manifest.json"
    if not synthetic_root.is_dir() or not manifest.is_file():
        raise PracticeAuditError(
            f"synthetic_package must contain manifest.json: {synthetic_root}"
        )
    if synthetic_root == target or synthetic_root in target.parents:
        raise PracticeAuditError(
            "Audit output cannot be inside the checksum-governed synthetic package."
        )
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise PracticeAuditError("Audit output must be a new or empty directory.")


def _validate_schemas_and_identity(
    session: Mapping[str, Any], draft: Mapping[str, Any]
) -> None:
    if session.get("artifact_schema") != SESSION_SCHEMA:
        raise PracticeAuditError("Practice session schema is unsupported.")
    if draft.get("artifact_schema") != DRAFT_SCHEMA:
        raise PracticeAuditError("Practice draft schema is unsupported.")
    workspace_id = session.get("workspace_id")
    if not isinstance(workspace_id, str) or WORKSPACE_ID_PATTERN.fullmatch(
        workspace_id
    ) is None:
        raise PracticeAuditError("Practice workspace_id is invalid.")
    if draft.get("workspace_id") != workspace_id:
        raise PracticeAuditError("Session and draft workspace IDs do not match.")
    reviewer = session.get("reviewer_display_name")
    if (
        not isinstance(reviewer, str)
        or not reviewer.strip()
        or reviewer != reviewer.strip()
        or len(reviewer) > 120
        or any(ord(character) < 32 for character in reviewer)
    ):
        raise PracticeAuditError("Practice reviewer_display_name is invalid.")
    if draft.get("reviewer_display_name") != reviewer:
        raise PracticeAuditError("Session and draft reviewer identities do not match.")
    for key, expected in SAFETY_FLAGS.items():
        if session.get(key) is not expected:
            raise PracticeAuditError(
                f"Practice session safety field {key} must be {expected}."
            )


def _synthetic_profile(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    schema = manifest.get("artifact_schema")
    profile = SYNTHETIC_PROFILES.get(str(schema))
    if profile is None:
        raise PracticeAuditError("Synthetic practice manifest schema is unsupported.")
    return profile


def _synthetic_cases(
    manifest: Mapping[str, Any],
    synthetic_root: Path,
    profile: Mapping[str, Any],
) -> list[dict[str, Any]]:
    raw_ids = manifest.get("case_ids")
    raw_cases = manifest.get("cases")
    if not isinstance(raw_ids, list) or not isinstance(raw_cases, list):
        raise PracticeAuditError("Synthetic manifest case lists are missing.")
    expected_ids = list(profile["case_ids"])
    if len(raw_ids) != len(expected_ids) or len(raw_cases) != len(expected_ids):
        raise PracticeAuditError(
            "Synthetic practice audit case coverage does not match its schema."
        )
    if raw_ids != expected_ids:
        raise PracticeAuditError("Synthetic case IDs are incomplete or reordered.")
    rows: list[dict[str, Any]] = []
    for case_id, raw in zip(expected_ids, raw_cases, strict=True):
        if not isinstance(raw, dict) or raw.get("case_id") != case_id:
            raise PracticeAuditError("Synthetic case rows do not match their IDs.")
        expected_text = raw.get("expected_primary")
        if expected_text not in EXPECTED_PRIMARY:
            raise PracticeAuditError(
                f"{case_id} has an unsupported expected_primary value."
            )
        challenge = raw.get("challenge")
        if not isinstance(challenge, str) or not challenge.strip():
            raise PracticeAuditError(f"{case_id} teaching challenge is missing.")
        answer_path = synthetic_root / "answer_key" / f"{case_id}_labels.png"
        declared_answer_hash = _required_sha256(
            raw.get("answer_label_sha256"), f"{case_id} answer hash"
        )
        if not answer_path.is_file() or _sha256(answer_path) != declared_answer_hash:
            raise PracticeAuditError(f"{case_id} answer mask checksum does not match.")
        try:
            answer_codes = _read_label_codes(answer_path)
        except (OSError, ReviewerWorkspaceError) as exc:
            raise PracticeAuditError(f"Could not decode {case_id} answer mask: {exc}") from exc
        if len(answer_codes) != 1024 or any(
            code not in REVIEWED_CODES for code in answer_codes
        ):
            raise PracticeAuditError(
                f"{case_id} teaching answer must contain 1,024 reviewed cells."
            )
        declared_counts = raw.get("label_counts")
        if not isinstance(declared_counts, dict):
            raise PracticeAuditError(f"{case_id} label_counts are missing.")
        observed_counts = {
            str(code): answer_codes.count(code) for code in ALL_CODES
        }
        if declared_counts != observed_counts:
            raise PracticeAuditError(f"{case_id} answer label counts do not match.")
        rows.append(
            {
                "case_id": case_id,
                "challenge": challenge.strip(),
                "expected_primary": EXPECTED_PRIMARY[expected_text],
                "answer_codes": answer_codes,
            }
        )
    return rows


def _session_cases(
    session: Mapping[str, Any], case_ids: Sequence[str]
) -> dict[str, dict[str, Any]]:
    raw_cases = session.get("cases")
    if not isinstance(raw_cases, list) or len(raw_cases) != len(case_ids):
        raise PracticeAuditError("Practice session case coverage is incomplete.")
    result: dict[str, dict[str, Any]] = {}
    for expected_id, raw in zip(case_ids, raw_cases, strict=True):
        if not isinstance(raw, dict):
            raise PracticeAuditError("Practice session cases must be JSON objects.")
        _require_exact_keys(raw, SESSION_CASE_KEYS, f"session case {expected_id}")
        if raw.get("practice_case_id") != expected_id:
            raise PracticeAuditError("Practice session case IDs are reordered or invalid.")
        if expected_id in result:
            raise PracticeAuditError(f"Duplicate practice session case: {expected_id}")
        result[expected_id] = raw
    return result


def _draft_attempts(
    draft: Mapping[str, Any], case_ids: Sequence[str]
) -> dict[str, dict[str, Any]]:
    attempts = draft.get("attempts")
    if not isinstance(attempts, dict) or list(attempts) != list(case_ids):
        raise PracticeAuditError("Practice draft attempt coverage or order is invalid.")
    case_index = draft.get("case_index")
    if (
        isinstance(case_index, bool)
        or not isinstance(case_index, int)
        or not 0 <= case_index < len(case_ids)
    ):
        raise PracticeAuditError("Practice draft case_index is invalid.")
    result: dict[str, dict[str, Any]] = {}
    for case_id in case_ids:
        raw = attempts[case_id]
        if not isinstance(raw, dict):
            raise PracticeAuditError(f"Draft attempt {case_id} must be an object.")
        _require_exact_keys(raw, DRAFT_ATTEMPT_KEYS, f"draft attempt {case_id}")
        result[case_id] = raw
    return result


def _read_and_validate_cells_csv(
    path: Path,
    session: Mapping[str, Any],
    session_cases: Mapping[str, Mapping[str, Any]],
    case_ids: Sequence[str],
) -> dict[str, dict[int, int]]:
    result: dict[str, dict[int, int]] = {case_id: {} for case_id in case_ids}
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != CSV_COLUMNS:
                raise PracticeAuditError("Practice cell CSV columns do not match the schema.")
            for line_number, row in enumerate(reader, start=2):
                if None in row:
                    raise PracticeAuditError(
                        f"Practice cell CSV row {line_number} has extra values."
                    )
                case_id = row["practice_case_id"]
                if case_id not in result:
                    raise PracticeAuditError(
                        f"Practice cell CSV row {line_number} has an unknown case ID."
                    )
                row_index = _csv_integer(
                    row["row_index"], f"CSV row {line_number} row_index"
                )
                column_index = _csv_integer(
                    row["column_index"], f"CSV row {line_number} column_index"
                )
                code = _csv_integer(
                    row["practice_label_code"],
                    f"CSV row {line_number} practice_label_code",
                )
                if not 0 <= row_index < 32 or not 0 <= column_index < 32:
                    raise PracticeAuditError(
                        f"Practice cell CSV row {line_number} has invalid coordinates."
                    )
                if code not in REVIEWED_CODES:
                    raise PracticeAuditError(
                        f"Practice cell CSV row {line_number} is not fully reviewed."
                    )
                if row["practice_label_name"] != LABEL_NAMES[code]:
                    raise PracticeAuditError(
                        f"Practice cell CSV row {line_number} label name does not match."
                    )
                index = row_index * 32 + column_index
                if index in result[case_id]:
                    raise PracticeAuditError(
                        f"Practice cell CSV has duplicate coordinate {case_id}/{index}."
                    )
                session_case = session_cases[case_id]
                expected_metadata = {
                    "practice_workspace_id": session["workspace_id"],
                    "reviewer_display_name": session["reviewer_display_name"],
                    "locked_at_utc": session_case["locked_at_utc"],
                    "confidence": session_case["confidence"],
                    "post_lock_feedback_revealed": "true",
                }
                for key, expected in expected_metadata.items():
                    if row[key] != expected:
                        raise PracticeAuditError(
                            f"Practice cell CSV row {line_number} {key} does not match."
                        )
                duration = _finite_number(
                    row["duration_seconds"],
                    f"CSV row {line_number} duration_seconds",
                )
                if not math.isclose(
                    duration,
                    _finite_number(
                        session_case["duration_seconds"],
                        f"{case_id} duration_seconds",
                    ),
                    rel_tol=0.0,
                    abs_tol=1e-9,
                ):
                    raise PracticeAuditError(
                        f"Practice cell CSV row {line_number} duration does not match."
                    )
                result[case_id][index] = code
    except (OSError, UnicodeError, csv.Error) as exc:
        raise PracticeAuditError(f"Could not read practice cell CSV: {exc}") from exc
    for case_id, cells in result.items():
        if set(cells) != set(range(1024)):
            raise PracticeAuditError(
                f"Practice cell CSV coverage is incomplete for {case_id}."
            )
    return result


def _validate_case_and_draft(
    session_case: Mapping[str, Any],
    draft: Mapping[str, Any],
    csv_cells: Mapping[int, int],
    answer_codes: Sequence[int],
    case_id: str,
) -> list[int]:
    if session_case.get("locked") is not True or draft.get("locked") is not True:
        raise PracticeAuditError(f"{case_id} is not locked in both exports.")
    if (
        session_case.get("post_lock_feedback_revealed") is not True
        or draft.get("revealed") is not True
    ):
        raise PracticeAuditError(f"{case_id} teaching feedback is not revealed.")
    labels = _label_list(session_case.get("practice_cell_codes"), f"{case_id} session")
    draft_labels = _label_list(draft.get("labels"), f"{case_id} draft")
    if labels != draft_labels:
        raise PracticeAuditError(f"{case_id} session and draft cell labels differ.")
    if labels != [csv_cells[index] for index in range(1024)]:
        raise PracticeAuditError(f"{case_id} CSV and JSON cell labels differ.")
    if len(answer_codes) != len(labels):
        raise PracticeAuditError(f"{case_id} answer and review geometry differ.")

    primary = session_case.get("primary_assessment")
    confidence = session_case.get("confidence")
    if primary not in PRIMARY_ASSESSMENTS or draft.get("primaryAssessment") != primary:
        raise PracticeAuditError(f"{case_id} primary assessment is invalid or inconsistent.")
    if confidence not in CONFIDENCE_VALUES or draft.get("confidence") != confidence:
        raise PracticeAuditError(f"{case_id} confidence is invalid or inconsistent.")
    ambiguity = _bounded_unique_strings(
        session_case.get("ambiguity_reason_codes"),
        AMBIGUITY_VALUES,
        f"{case_id} ambiguity reasons",
    )
    draft_ambiguity = _bounded_unique_strings(
        draft.get("ambiguity"), AMBIGUITY_VALUES, f"{case_id} draft ambiguity"
    )
    if ambiguity != draft_ambiguity:
        raise PracticeAuditError(f"{case_id} ambiguity reasons differ across exports.")
    if any(code in (3, 4) for code in labels) and not ambiguity:
        raise PracticeAuditError(
            f"{case_id} uncertainty/artifact labels require an ambiguity reason."
        )
    layers = _bounded_unique_strings(
        session_case.get("evidence_layers_viewed"),
        EVIDENCE_LAYERS,
        f"{case_id} evidence layers",
    )
    draft_layers = _bounded_unique_strings(
        draft.get("visitedLayers"), EVIDENCE_LAYERS, f"{case_id} draft layers"
    )
    if layers != draft_layers or not layers:
        raise PracticeAuditError(f"{case_id} evidence-layer records are inconsistent.")
    notes = session_case.get("notes")
    if not isinstance(notes, str) or len(notes) > 1000 or draft.get("notes") != notes:
        raise PracticeAuditError(f"{case_id} reasoning notes are invalid or inconsistent.")
    if draft.get("history") != [] or draft.get("future") != []:
        raise PracticeAuditError(f"{case_id} locked draft retains editable history.")
    for field in ("started_at_utc", "locked_at_utc"):
        if draft.get(field) != session_case.get(field):
            raise PracticeAuditError(f"{case_id} {field} differs across exports.")
    draft_duration = _finite_number(
        draft.get("duration_seconds"), f"{case_id} draft duration_seconds"
    )
    session_duration = _finite_number(
        session_case.get("duration_seconds"), f"{case_id} session duration_seconds"
    )
    if abs(draft_duration - session_duration) > 0.051:
        raise PracticeAuditError(f"{case_id} duration differs across exports.")
    return labels


def _score(selected: Sequence[int], answer: Sequence[int]) -> dict[str, int | float]:
    correct = true_positive = false_positive = false_negative = 0
    for predicted, truth in zip(selected, answer, strict=True):
        if predicted == truth:
            correct += 1
        if predicted == 1 and truth == 1:
            true_positive += 1
        elif predicted == 1 and truth != 1:
            false_positive += 1
        elif predicted != 1 and truth == 1:
            false_negative += 1
    denominator = 2 * true_positive + false_positive + false_negative
    return {
        "accuracy": correct / len(answer),
        "temporary_flood_dice": (
            2 * true_positive / denominator if denominator else 1.0
        ),
        "correct_cells": correct,
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
    }


def _require_score(
    observed: object, expected: Mapping[str, int | float], label: str
) -> None:
    if not isinstance(observed, dict):
        raise PracticeAuditError(f"{label} score is missing.")
    _require_exact_keys(observed, SCORE_KEYS, f"{label} score")
    for key, expected_value in expected.items():
        value = _finite_number(observed.get(key), f"{label} score {key}")
        if isinstance(expected_value, int):
            if not value.is_integer() or int(value) != expected_value:
                raise PracticeAuditError(f"{label} score {key} does not reproduce.")
        elif not math.isclose(
            value, expected_value, rel_tol=0.0, abs_tol=1e-12
        ):
            raise PracticeAuditError(f"{label} score {key} does not reproduce.")


def _practice_summary(
    case_metrics: Sequence[Mapping[str, Any]],
    confusion: Mapping[tuple[int, int], int],
    total_active_seconds: float,
    *,
    practice_stage: str,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    case_count = len(case_metrics)
    total_cells = case_count * 1024
    total_correct = sum(int(row["correct_cells"]) for row in case_metrics)
    true_positive = sum(int(row["true_positive"]) for row in case_metrics)
    false_positive = sum(int(row["false_positive"]) for row in case_metrics)
    false_negative = sum(int(row["false_negative"]) for row in case_metrics)
    aggregate_denominator = 2 * true_positive + false_positive + false_negative
    aggregate_dice = (
        2 * true_positive / aggregate_denominator if aggregate_denominator else 1.0
    )
    flood_cases = [
        row for row in case_metrics if int(row["truth_temporary_flood_cells"]) > 0
    ]
    mean_flood_case_dice = (
        sum(float(row["temporary_flood_dice"]) for row in flood_cases)
        / len(flood_cases)
        if flood_cases
        else 1.0
    )
    zero_dice_flood_cases = [
        str(row["practice_case_id"])
        for row in flood_cases
        if math.isclose(float(row["temporary_flood_dice"]), 0.0, abs_tol=1e-12)
    ]
    primary_matches = sum(bool(row["primary_assessment_matches"]) for row in case_metrics)
    note_count = sum(bool(row["reasoning_note_present"]) for row in case_metrics)
    all_layer_count = sum(bool(row["all_evidence_layers_viewed"]) for row in case_metrics)
    observed = {
        "aggregate_temporary_flood_dice": aggregate_dice,
        "mean_flood_present_case_dice": mean_flood_case_dice,
        "primary_assessment_match_rate": primary_matches / case_count,
        "reasoning_note_completion_rate": note_count / case_count,
        "all_layer_inspection_rate": all_layer_count / case_count,
        "zero_dice_flood_present_case_count": len(zero_dice_flood_cases),
    }
    passed = {
        "aggregate_temporary_flood_dice": (
            aggregate_dice
            >= float(PRACTICE_THRESHOLDS["minimum_aggregate_temporary_flood_dice"])
        ),
        "mean_flood_present_case_dice": (
            mean_flood_case_dice
            >= float(PRACTICE_THRESHOLDS["minimum_mean_flood_present_case_dice"])
        ),
        "primary_assessment_match_rate": (
            observed["primary_assessment_match_rate"]
            >= float(PRACTICE_THRESHOLDS["minimum_primary_assessment_match_rate"])
        ),
        "reasoning_note_completion_rate": (
            observed["reasoning_note_completion_rate"]
            >= float(PRACTICE_THRESHOLDS["required_reasoning_note_completion_rate"])
        ),
        "all_layer_inspection_rate": (
            observed["all_layer_inspection_rate"]
            >= float(PRACTICE_THRESHOLDS["required_all_layer_inspection_rate"])
        ),
        "zero_dice_flood_present_case_count": (
            len(zero_dice_flood_cases)
            <= int(PRACTICE_THRESHOLDS["maximum_zero_dice_flood_present_cases"])
        ),
    }
    failed = [name for name, value in passed.items() if not value]
    if practice_stage == "targeted_remediation":
        next_step_status = (
            "remediation_complete_needs_additional_targeted_practice"
            if failed
            else "remediation_complete_ready_for_real_data_orientation"
        )
    else:
        next_step_status = (
            "first_pass_complete_needs_targeted_remediation"
            if failed
            else "first_pass_complete_ready_for_additional_blinded_practice"
        )
    off_diagonal = [
        {
            "truth_label_code": truth,
            "predicted_label_code": predicted,
            "cell_count": count,
        }
        for (truth, predicted), count in confusion.items()
        if truth != predicted and count
    ]
    off_diagonal.sort(key=lambda row: (-row["cell_count"], row["truth_label_code"], row["predicted_label_code"]))
    summary = {
        "case_count": case_count,
        "cell_count": total_cells,
        "correct_cells": total_correct,
        "overall_accuracy": total_correct / total_cells,
        "mean_case_accuracy": sum(float(row["accuracy"]) for row in case_metrics)
        / case_count,
        "mean_case_temporary_flood_dice": sum(
            float(row["temporary_flood_dice"]) for row in case_metrics
        )
        / case_count,
        "aggregate_temporary_flood_precision": (
            true_positive / (true_positive + false_positive)
            if true_positive + false_positive
            else 1.0
        ),
        "aggregate_temporary_flood_recall": (
            true_positive / (true_positive + false_negative)
            if true_positive + false_negative
            else 1.0
        ),
        "aggregate_temporary_flood_dice": aggregate_dice,
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "flood_present_case_count": len(flood_cases),
        "mean_flood_present_case_dice": mean_flood_case_dice,
        "zero_dice_flood_present_case_ids": zero_dice_flood_cases,
        "primary_assessment_match_count": primary_matches,
        "primary_assessment_match_rate": primary_matches / case_count,
        "reasoning_note_present_count": note_count,
        "all_evidence_layers_viewed_case_count": all_layer_count,
        "total_active_seconds": total_active_seconds,
        "largest_off_diagonal_confusions": off_diagonal[:5],
    }
    heuristics = {
        "purpose": "practice learning guidance only; not formal calibration thresholds",
        "practice_stage": practice_stage,
        "thresholds": dict(PRACTICE_THRESHOLDS),
        "observed": observed,
        "passed": passed,
        "failed_heuristics": failed,
    }
    return summary, heuristics, next_step_status


def _write_audit_outputs(
    target: Path,
    *,
    audited_at: str,
    workspace_id: str,
    reviewer_display_name: str,
    exported_at: str,
    saved_at: str,
    input_hashes: Mapping[str, str],
    case_metrics: Sequence[Mapping[str, Any]],
    confusion: Mapping[tuple[int, int], int],
    summary_metrics: Mapping[str, Any],
    heuristics: Mapping[str, Any],
    next_step_status: str,
    source_package_schema: str,
    practice_stage: str,
) -> Path:
    recommended_focus = (
        [
            "supported urban flood versus urban layover/double-bounce ambiguity",
            "temporal mismatch versus supported temporary flood",
            "pre/post misregistration as artifact rather than semantic uncertainty",
            "uncertain mixed-boundary cells rather than dry closure",
            "case-level primary assessment aligned with multiclass geometry",
        ]
        if practice_stage == "targeted_remediation"
        else [
            "temporary flood versus uncertain water change",
            "flooded vegetation",
            "agricultural and temporal ambiguity",
            "complete eight-layer evidence inspection",
            "written evidence reasoning for every case",
        ]
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{target.name}.tmp-", dir=target.parent)
    )
    try:
        case_path = temporary / "case_metrics.csv"
        confusion_path = temporary / "confusion_matrix.csv"
        input_path = temporary / "input_hashes.json"
        _write_case_metrics(case_path, case_metrics)
        _write_confusion_matrix(confusion_path, confusion)

        input_payload: dict[str, Any] = {
            "artifact_schema": INPUT_HASH_SCHEMA,
            "audited_at_utc": audited_at,
            **SAFETY_FLAGS,
            "input_artifact_sha256": dict(sorted(input_hashes.items())),
            "assumptions": (
                "Hashes identify conceptual practice exports and the verified "
                "synthetic manifest; they do not identify formal labels."
            ),
        }
        input_payload["manifest_sha256"] = _canonical_hash(input_payload)
        _write_json(input_path, input_payload)

        output_hashes = {
            "case_metrics.csv": _sha256(case_path),
            "confusion_matrix.csv": _sha256(confusion_path),
            "input_hashes.json": _sha256(input_path),
        }
        summary: dict[str, Any] = {
            "artifact_schema": AUDIT_SCHEMA,
            "audited_at_utc": audited_at,
            "workspace_id": workspace_id,
            "reviewer_display_name": reviewer_display_name,
            "session_exported_at_utc": exported_at,
            "draft_saved_at_utc": saved_at,
            "validation_status": "passed",
            "integrity_issue_count": 0,
            **SAFETY_FLAGS,
            "formal_calibration_readiness_assessed": False,
            "formal_calibration_status": "not_assessed_by_practice_audit",
            "source_package_schema": source_package_schema,
            "practice_stage": practice_stage,
            "next_step_status": next_step_status,
            "summary_metrics": dict(summary_metrics),
            "practice_heuristics": dict(heuristics),
            "recommended_focus": recommended_focus,
            "input_artifact_sha256": dict(sorted(input_hashes.items())),
            "output_artifact_sha256": output_hashes,
            "assumptions": (
                "Successful integrity validation proves only that the conceptual "
                "practice exports are internally reproducible. It is not a passing "
                "reviewer-calibration receipt and cannot unlock formal queries."
            ),
        }
        summary["summary_sha256"] = _canonical_hash(summary)
        _write_json(temporary / "summary.json", summary)

        if target.exists():
            target.rmdir()
        temporary.replace(target)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return target


def _write_case_metrics(
    path: Path, rows: Sequence[Mapping[str, Any]]
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CASE_METRIC_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for raw in rows:
            row = dict(raw)
            for key in ("accuracy", "temporary_flood_dice", "duration_seconds"):
                row[key] = _csv_number(float(row[key]))
            for key in (
                "primary_assessment_matches",
                "all_evidence_layers_viewed",
                "reasoning_note_present",
            ):
                row[key] = str(bool(row[key])).lower()
            row["missing_evidence_layers"] = "|".join(row["missing_evidence_layers"])
            row["ambiguity_reason_codes"] = "|".join(row["ambiguity_reason_codes"])
            writer.writerow(row)


def _write_confusion_matrix(
    path: Path, confusion: Mapping[tuple[int, int], int]
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CONFUSION_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for truth in REVIEWED_CODES:
            for predicted in REVIEWED_CODES:
                writer.writerow(
                    {
                        "truth_label_code": truth,
                        "truth_label_name": LABEL_NAMES[truth],
                        "predicted_label_code": predicted,
                        "predicted_label_name": LABEL_NAMES[predicted],
                        "cell_count": confusion[(truth, predicted)],
                    }
                )


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, PracticeAuditError) as exc:
        if isinstance(exc, PracticeAuditError):
            raise
        raise PracticeAuditError(f"Could not read {label}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PracticeAuditError(f"{label} must be a JSON object.")
    return payload


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PracticeAuditError(f"JSON contains duplicate key: {key}")
        result[key] = value
    return result


def _require_exact_keys(
    value: Mapping[str, Any], expected: set[str], label: str
) -> None:
    if set(value) != expected:
        missing = sorted(expected - set(value))
        extra = sorted(set(value) - expected)
        raise PracticeAuditError(
            f"{label} schema keys differ; missing={missing}, extra={extra}."
        )


def _label_list(value: object, label: str) -> list[int]:
    if not isinstance(value, list) or len(value) != 1024:
        raise PracticeAuditError(f"{label} must contain exactly 1,024 labels.")
    result: list[int] = []
    for raw in value:
        if isinstance(raw, bool) or not isinstance(raw, int) or raw not in REVIEWED_CODES:
            raise PracticeAuditError(f"{label} contains an invalid or unreviewed label.")
        result.append(raw)
    return result


def _bounded_unique_strings(
    value: object,
    allowed: Sequence[str],
    label: str,
) -> list[str]:
    if not isinstance(value, list):
        raise PracticeAuditError(f"{label} must be a list.")
    if any(not isinstance(item, str) or item not in allowed for item in value):
        raise PracticeAuditError(f"{label} contains an unsupported value.")
    if len(value) != len(set(value)):
        raise PracticeAuditError(f"{label} contains duplicate values.")
    return list(value)


def _parse_utc(value: object, label: str) -> datetime:
    if not isinstance(value, str) or UTC_TIMESTAMP_PATTERN.fullmatch(value) is None:
        raise PracticeAuditError(f"{label} must be a second-precision UTC timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PracticeAuditError(f"{label} is not a valid timestamp.") from exc
    return parsed


def _utc_timestamp(value: datetime, label: str) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise PracticeAuditError(f"{label} must be timezone-aware.")
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _require_non_overlapping_intervals(
    intervals: Sequence[tuple[datetime, datetime, str]]
) -> None:
    ordered = sorted(intervals)
    for previous, current in zip(ordered, ordered[1:]):
        if current[0] < previous[1]:
            raise PracticeAuditError(
                f"Practice case intervals overlap: {previous[2]} and {current[2]}."
            )


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise PracticeAuditError(f"{label} must be numeric.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise PracticeAuditError(f"{label} must be numeric.") from exc
    if not math.isfinite(number):
        raise PracticeAuditError(f"{label} must be finite.")
    return number


def _csv_integer(value: object, label: str) -> int:
    text = str(value)
    if re.fullmatch(r"0|[1-9][0-9]*", text) is None:
        raise PracticeAuditError(f"{label} must be a canonical non-negative integer.")
    return int(text)


def _required_sha256(value: object, label: str) -> str:
    text = str(value).strip().lower()
    if re.fullmatch(r"[0-9a-f]{64}", text) is None:
        raise PracticeAuditError(f"{label} must be a complete SHA-256.")
    return text


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise PracticeAuditError(f"Could not hash input {path}: {exc}") from exc
    return digest.hexdigest()


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _csv_number(value: float) -> str:
    return f"{value:.12f}".rstrip("0").rstrip(".")
