"""Reference-mask legal gate checks for real-data validation and ML labels."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pandas as pd

REFERENCE_GATE_REQUIRED_COLUMNS: tuple[str, ...] = (
    "source_name",
    "study_area",
    "request_status",
    "request_sent_date",
    "response_date",
    "geometry_access",
    "local_analysis_allowed",
    "derived_metrics_allowed",
    "screenshots_demo_allowed",
    "redistribution_allowed",
    "citation_required",
    "ml_label_use_allowed",
    "blocking_decision",
)

REFERENCE_GATE_OUTPUT_COLUMNS: tuple[str, ...] = (
    *REFERENCE_GATE_REQUIRED_COLUMNS,
    "reference_validation_allowed",
    "ml_label_allowed",
    "gate_status",
    "reason_blocked",
)

AFFIRMATIVE_VALUES = {"yes", "true", "allowed", "confirmed", "granted"}
GEOMETRY_CLEAR_VALUES = {"confirmed", "available", "granted", "yes"}
REDISTRIBUTION_CLEAR_VALUES = {
    "redistributable",
    "reference_only",
    "allowed",
    "yes",
}
CITATION_CLEAR_VALUES = {
    "yes",
    "no",
    "required",
    "not_required",
    "provider_citation_required",
}
VALIDATION_DECISIONS = {
    "cleared_for_local_validation",
    "cleared_reference_only",
    "cleared_for_local_validation_reference_only",
}


class ReferenceGateError(ValueError):
    """Raised when reference-mask gate inputs are invalid."""


def default_reference_gate_rows() -> pd.DataFrame:
    """Return the current blocked provider-response gate rows."""

    return pd.DataFrame(
        [
            {
                "source_name": "UNOSAT/UNITAR Mae Sai reference target",
                "study_area": "Chiang Rai / Mae Sai 2024",
                "request_status": "sent_waiting_response",
                "request_sent_date": "2026-07-03",
                "response_date": "no_response",
                "geometry_access": "unresolved",
                "local_analysis_allowed": "unresolved",
                "derived_metrics_allowed": "unresolved",
                "screenshots_demo_allowed": "unresolved",
                "redistribution_allowed": "unresolved",
                "citation_required": "yes_expected",
                "ml_label_use_allowed": "unresolved",
                "blocking_decision": "blocked_provider_response_pending",
            },
            {
                "source_name": "GISTDA official flood product candidate",
                "study_area": "Chiang Rai / Mae Sai 2024 and Hat Yai / Songkhla 2025",
                "request_status": "sent_waiting_response",
                "request_sent_date": "2026-07-03",
                "response_date": "no_response",
                "geometry_access": "unresolved",
                "local_analysis_allowed": "unresolved",
                "derived_metrics_allowed": "unresolved",
                "screenshots_demo_allowed": "unresolved",
                "redistribution_allowed": "unresolved",
                "citation_required": "yes_expected",
                "ml_label_use_allowed": "unresolved",
                "blocking_decision": "blocked_provider_response_pending",
            },
            {
                "source_name": "International Charter Activation 1004",
                "study_area": "Hat Yai / Songkhla 2025",
                "request_status": "ready_to_send_not_sent",
                "request_sent_date": "not_sent",
                "response_date": "no_response",
                "geometry_access": "unresolved",
                "local_analysis_allowed": "unresolved",
                "derived_metrics_allowed": "unresolved",
                "screenshots_demo_allowed": "unresolved",
                "redistribution_allowed": "unresolved",
                "citation_required": "yes_expected",
                "ml_label_use_allowed": "unresolved",
                "blocking_decision": "blocked_activation_product_terms_unconfirmed",
            },
            {
                "source_name": "Sentinel Asia Southern Thailand 2025",
                "study_area": "Hat Yai / Songkhla 2025",
                "request_status": "ready_to_send_not_sent",
                "request_sent_date": "not_sent",
                "response_date": "no_response",
                "geometry_access": "unresolved",
                "local_analysis_allowed": "unresolved",
                "derived_metrics_allowed": "unresolved",
                "screenshots_demo_allowed": "unresolved",
                "redistribution_allowed": "unresolved",
                "citation_required": "yes_expected",
                "ml_label_use_allowed": "unresolved",
                "blocking_decision": "blocked_product_file_terms_unconfirmed",
            },
        ]
    )


def build_reference_gate_report(
    source_frame: pd.DataFrame,
    *,
    study_area_contains: str | None = None,
) -> pd.DataFrame:
    """Return reference-mask gate status rows with explicit blockers.

    ``reference_validation_allowed`` is intentionally separate from
    ``ml_label_allowed`` because a provider may permit local validation while
    forbidding label reuse for ML training.
    """

    _validate_columns(source_frame, REFERENCE_GATE_REQUIRED_COLUMNS, "reference gate")
    frame = source_frame.copy()
    for column in REFERENCE_GATE_REQUIRED_COLUMNS:
        frame[column] = frame[column].astype(str).str.strip()
        if frame[column].eq("").any():
            raise ReferenceGateError(f"Column {column} must not contain blank values.")

    if study_area_contains:
        mask = frame["study_area"].str.contains(study_area_contains, case=False, regex=False)
        frame = frame.loc[mask].copy()

    blockers = frame.apply(_reference_gate_blockers, axis=1)
    validation_allowed = blockers.map(lambda items: len(items) == 0)
    ml_allowed = validation_allowed & frame["ml_label_use_allowed"].map(_is_affirmative)

    report = frame.copy()
    report["reference_validation_allowed"] = validation_allowed
    report["ml_label_allowed"] = ml_allowed
    report["gate_status"] = validation_allowed.map(
        {True: "cleared_for_local_validation", False: "blocked"}
    )
    report["reason_blocked"] = blockers.map(
        lambda items: "none" if not items else "; ".join(items)
    )
    return report.loc[:, REFERENCE_GATE_OUTPUT_COLUMNS]


def write_reference_gate_report(
    source_frame: pd.DataFrame,
    output_path: str | Path,
    *,
    study_area_contains: str | None = None,
) -> Path:
    """Write a reference-gate report CSV."""

    target = Path(output_path)
    if target.suffix.lower() != ".csv":
        raise ReferenceGateError("Reference gate reports must be CSV files.")
    target.parent.mkdir(parents=True, exist_ok=True)
    report = build_reference_gate_report(
        source_frame,
        study_area_contains=study_area_contains,
    )
    report.to_csv(target, index=False)
    return target


def _reference_gate_blockers(row: pd.Series) -> list[str]:
    blockers: list[str] = []
    if _clean(row["geometry_access"]) not in GEOMETRY_CLEAR_VALUES:
        blockers.append("geometry access not confirmed")
    if not _is_affirmative(row["local_analysis_allowed"]):
        blockers.append("local analysis permission not confirmed")
    if not _is_affirmative(row["derived_metrics_allowed"]):
        blockers.append("derived metrics permission not confirmed")
    if not _is_affirmative(row["screenshots_demo_allowed"]):
        blockers.append("screenshots/demo permission not confirmed")
    if _clean(row["redistribution_allowed"]) not in REDISTRIBUTION_CLEAR_VALUES:
        blockers.append("redistribution/reference-only status not confirmed")
    if _clean(row["citation_required"]) not in CITATION_CLEAR_VALUES:
        blockers.append("citation requirement not resolved")
    if _clean(row["blocking_decision"]) not in VALIDATION_DECISIONS:
        blockers.append("blocking_decision is not cleared for local validation")
    return blockers


def _is_affirmative(value: object) -> bool:
    return _clean(value) in AFFIRMATIVE_VALUES


def _clean(value: object) -> str:
    return str(value).strip().lower()


def _validate_columns(
    frame: pd.DataFrame,
    required_columns: Sequence[str],
    frame_name: str,
) -> None:
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ReferenceGateError(
            f"Missing required {frame_name} column(s): {', '.join(missing)}"
        )
