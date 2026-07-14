"""Formal import of completed human adjudication forms.

This module is deliberately fail-closed.  It binds a completed CSV to the
exact queue and locked A/B annotation log that produced the work, resolves
every currently open queue item, appends the batch to the tamper-evident
adjudication log, and writes a self-hashed import receipt.  It never creates or
infers a human decision.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from floodguard.label_factory.adjudication import (
    AdjudicationError,
    AdjudicationOutcome,
    AdjudicationQueueItem,
    AdjudicationRecord,
    QUEUE_REASON_CODES,
    ReviewerPair,
    append_adjudication_records,
    build_adjudication_record,
    load_adjudication_log,
    pair_locked_annotations,
    unresolved_queue_items,
    validate_queue_item_sources,
)
from floodguard.label_factory.annotations import (
    AMBIGUITY_REASON_CODES,
    AnnotationRecord,
    load_annotation_log,
)
from floodguard.label_factory.review_workflow import load_adjudication_queue_csv


ADJUDICATION_IMPORT_SCHEMA = "floodguard.completed_adjudications.v1"
ADJUDICATION_IMPORT_RECEIPT_SCHEMA = "floodguard.adjudication_import_receipt.v1"

COMPLETED_ADJUDICATION_COLUMNS: tuple[str, ...] = (
    "queue_id",
    "adjudication_id",
    "adjudicator_id",
    "outcome",
    "resolution_reason_codes",
    "final_primary_class",
    "final_geometry",
    "notes",
    "protocol_version",
    "resolved_at_utc",
    "locked_at_utc",
)

RESOLUTION_REASON_CODES: frozenset[str] = frozenset(
    set(QUEUE_REASON_CODES) | set(AMBIGUITY_REASON_CODES)
)


class AdjudicationImportError(ValueError):
    """Raised when formal adjudication interchange cannot be trusted."""


@dataclass(frozen=True, slots=True)
class AdjudicationImportReceipt:
    """Self-hashed lineage receipt for one exact-coverage import batch."""

    imported_at_utc: str
    completed_adjudications_path: str
    adjudication_queue_path: str
    annotation_log_path: str
    adjudication_log_path: str
    completed_adjudications_sha256: str
    adjudication_queue_sha256: str
    annotation_log_sha256: str
    adjudication_log_sha256_before: str | None
    adjudication_log_sha256_after: str
    reviewer_a_id: str
    reviewer_b_id: str
    source_annotation_ids: tuple[str, ...]
    source_annotation_sha256_by_id: tuple[tuple[str, str], ...]
    queue_item_count: int
    previously_resolved_count: int
    open_queue_count_before: int
    imported_count: int
    remaining_open_queue_count: int
    submitted_queue_ids: tuple[str, ...]
    imported_adjudication_ids: tuple[str, ...]
    appended_record_sha256: tuple[str, ...]
    protocol_versions: tuple[str, ...]
    receipt_sha256: str

    def to_dict(self, *, include_self_hash: bool = True) -> dict[str, Any]:
        """Return the stable public receipt with permanent safety fields."""

        payload: dict[str, Any] = {
            "artifact_schema": ADJUDICATION_IMPORT_RECEIPT_SCHEMA,
            "input_schema": ADJUDICATION_IMPORT_SCHEMA,
            "import_mode": "exact_open_queue_coverage",
            "coverage_complete": True,
            "imported_at_utc": self.imported_at_utc,
            "completed_adjudications_path": self.completed_adjudications_path,
            "adjudication_queue_path": self.adjudication_queue_path,
            "annotation_log_path": self.annotation_log_path,
            "adjudication_log_path": self.adjudication_log_path,
            "completed_adjudications_sha256": self.completed_adjudications_sha256,
            "adjudication_queue_sha256": self.adjudication_queue_sha256,
            "annotation_log_sha256": self.annotation_log_sha256,
            "adjudication_log_sha256_before": self.adjudication_log_sha256_before,
            "adjudication_log_sha256_after": self.adjudication_log_sha256_after,
            "reviewer_a_id": self.reviewer_a_id,
            "reviewer_b_id": self.reviewer_b_id,
            "source_annotation_ids": list(self.source_annotation_ids),
            "source_annotation_sha256_by_id": dict(
                self.source_annotation_sha256_by_id
            ),
            "queue_item_count": self.queue_item_count,
            "previously_resolved_count": self.previously_resolved_count,
            "open_queue_count_before": self.open_queue_count_before,
            "imported_count": self.imported_count,
            "remaining_open_queue_count": self.remaining_open_queue_count,
            "submitted_queue_ids": list(self.submitted_queue_ids),
            "imported_adjudication_ids": list(self.imported_adjudication_ids),
            "appended_record_sha256": list(self.appended_record_sha256),
            "protocol_versions": list(self.protocol_versions),
            "report_only": True,
            "requires_frozen_labelset": True,
            "eligible_for_query_model_training": False,
            "eligible_for_decision_layer": False,
            "eligible_for_fpps": False,
            "eligible_for_warning": False,
        }
        if include_self_hash:
            payload["receipt_sha256"] = self.receipt_sha256
        return payload


def import_completed_adjudications(
    completed_adjudications: str | Path,
    *,
    adjudication_queue: str | Path,
    annotation_log: str | Path,
    adjudication_log: str | Path,
    receipt_json: str | Path,
    reviewer_a_id: str,
    reviewer_b_id: str,
    imported_at_utc: datetime,
) -> AdjudicationImportReceipt:
    """Validate and append a complete batch of real human resolutions.

    The submitted CSV must cover every queue item that is still unresolved.
    Partial import is intentionally unsupported because it would require a
    separately approved partial-mode protocol and receipt.
    """

    completed_path = _existing_file(completed_adjudications, "completed adjudications")
    queue_path = _existing_file(adjudication_queue, "adjudication queue")
    annotation_path = _existing_file(annotation_log, "annotation log")
    log_path = Path(adjudication_log)
    receipt_path = Path(receipt_json)
    _require_distinct_paths(
        completed_path,
        queue_path,
        annotation_path,
        log_path,
        receipt_path,
    )
    if receipt_path.exists():
        raise AdjudicationImportError(
            f"Immutable import receipt already exists: {receipt_path}"
        )
    if log_path.exists() and not log_path.is_file():
        raise AdjudicationImportError(
            f"Adjudication log path is not a file: {log_path}"
        )
    imported_at = _as_utc(imported_at_utc, "imported_at_utc")
    reviewer_a = _required_text(reviewer_a_id, "reviewer_a_id")
    reviewer_b = _required_text(reviewer_b_id, "reviewer_b_id")
    if reviewer_a == reviewer_b:
        raise AdjudicationImportError("reviewer_a_id and reviewer_b_id must differ.")

    queue_items = load_adjudication_queue_csv(queue_path)
    if not queue_items:
        raise AdjudicationImportError("Adjudication queue contains no items to import.")
    annotations = load_annotation_log(annotation_path)
    pairs = pair_locked_annotations(
        annotations,
        reviewer_a_id=reviewer_a,
        reviewer_b_id=reviewer_b,
    )
    pair_by_key = _pair_index(pairs)
    for queue_item in queue_items:
        pair = pair_by_key.get((queue_item.event_id, queue_item.query_region_id))
        if pair is None:
            raise AdjudicationImportError(
                f"Queue item {queue_item.queue_id} has no exact locked reviewer pair."
            )
        validate_queue_item_sources(queue_item, pair)

    existing = load_adjudication_log(log_path)
    unresolved = unresolved_queue_items(queue_items, existing)
    if not unresolved:
        raise AdjudicationImportError(
            "The exact queue is already fully resolved; there is nothing to import."
        )
    rows = _read_completed_rows(completed_path)
    expected_queue_ids = {item.queue_id for item in unresolved}
    submitted_queue_ids = [row["queue_id"] for row in rows]
    if len(submitted_queue_ids) != len(set(submitted_queue_ids)):
        raise AdjudicationImportError(
            "Completed adjudication CSV contains duplicate queue_id values."
        )
    submitted_set = set(submitted_queue_ids)
    if submitted_set != expected_queue_ids:
        raise AdjudicationImportError(
            "Completed adjudication CSV must exactly cover every currently open queue item; "
            f"missing={sorted(expected_queue_ids - submitted_set)}, "
            f"extra={sorted(submitted_set - expected_queue_ids)}."
        )

    queue_by_id = {item.queue_id: item for item in unresolved}
    existing_adjudication_ids = {record.adjudication_id for record in existing}
    imported_adjudication_ids: set[str] = set()
    records: list[AdjudicationRecord] = []
    for row_number, row in enumerate(rows, 2):
        adjudication_id = _required_text(
            row["adjudication_id"], f"row {row_number} adjudication_id"
        )
        if (
            adjudication_id in imported_adjudication_ids
            or adjudication_id in existing_adjudication_ids
        ):
            raise AdjudicationImportError(
                f"Duplicate or already-imported adjudication_id: {adjudication_id}"
            )
        imported_adjudication_ids.add(adjudication_id)
        queue_item = queue_by_id[row["queue_id"]]
        pair = pair_by_key[(queue_item.event_id, queue_item.query_region_id)]
        records.append(
            _record_from_row(
                row,
                row_number=row_number,
                queue_item=queue_item,
                pair=pair,
                adjudication_id=adjudication_id,
                reviewer_a_id=reviewer_a,
                reviewer_b_id=reviewer_b,
            )
        )

    latest_lock = max(record.locked_at_utc for record in records)
    if imported_at < latest_lock:
        raise AdjudicationImportError(
            "imported_at_utc must not precede a submitted locked_at_utc timestamp."
        )
    log_hash_before = _file_sha256(log_path) if log_path.exists() else None
    record_hashes = append_adjudication_records(log_path, records)

    combined = load_adjudication_log(log_path)
    remaining = unresolved_queue_items(queue_items, combined)
    if remaining:
        raise AdjudicationImportError(
            "Adjudication log still has unresolved queue items after exact-coverage import."
        )
    source_annotation_hashes = _source_annotation_hashes(queue_items)
    receipt = AdjudicationImportReceipt(
        imported_at_utc=_iso_utc(imported_at),
        completed_adjudications_path=str(completed_path),
        adjudication_queue_path=str(queue_path),
        annotation_log_path=str(annotation_path),
        adjudication_log_path=str(log_path),
        completed_adjudications_sha256=_file_sha256(completed_path),
        adjudication_queue_sha256=_file_sha256(queue_path),
        annotation_log_sha256=_file_sha256(annotation_path),
        adjudication_log_sha256_before=log_hash_before,
        adjudication_log_sha256_after=_file_sha256(log_path),
        reviewer_a_id=reviewer_a,
        reviewer_b_id=reviewer_b,
        source_annotation_ids=tuple(sorted(source_annotation_hashes)),
        source_annotation_sha256_by_id=tuple(sorted(source_annotation_hashes.items())),
        queue_item_count=len(queue_items),
        previously_resolved_count=len(existing),
        open_queue_count_before=len(unresolved),
        imported_count=len(records),
        remaining_open_queue_count=0,
        submitted_queue_ids=tuple(sorted(submitted_queue_ids)),
        imported_adjudication_ids=tuple(
            sorted(record.adjudication_id for record in records)
        ),
        appended_record_sha256=record_hashes,
        protocol_versions=tuple(sorted({record.protocol_version for record in records})),
        receipt_sha256="",
    )
    receipt = replace(
        receipt,
        receipt_sha256=_canonical_sha256(receipt.to_dict(include_self_hash=False)),
    )
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    with receipt_path.open("x", encoding="utf-8") as handle:
        json.dump(receipt.to_dict(), handle, ensure_ascii=True, sort_keys=True, indent=2)
        handle.write("\n")
    return receipt


def _read_completed_rows(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames
            if fieldnames is None:
                raise AdjudicationImportError(
                    "Completed adjudication CSV has no header row."
                )
            if len(fieldnames) != len(set(fieldnames)):
                raise AdjudicationImportError(
                    "Completed adjudication CSV contains duplicate column names."
                )
            if tuple(fieldnames) != COMPLETED_ADJUDICATION_COLUMNS:
                missing = sorted(set(COMPLETED_ADJUDICATION_COLUMNS) - set(fieldnames))
                extra = sorted(set(fieldnames) - set(COMPLETED_ADJUDICATION_COLUMNS))
                raise AdjudicationImportError(
                    "Completed adjudication CSV columns or order do not match the formal "
                    f"{ADJUDICATION_IMPORT_SCHEMA} contract; missing={missing}, extra={extra}."
                )
            rows: list[dict[str, str]] = []
            for row_number, row in enumerate(reader, 2):
                if None in row or any(value is None for value in row.values()):
                    raise AdjudicationImportError(
                        f"Completed adjudication CSV row {row_number} has the wrong field count."
                    )
                rows.append({key: str(value).strip() for key, value in row.items()})
    except (OSError, UnicodeError, csv.Error) as exc:
        if isinstance(exc, AdjudicationImportError):
            raise
        raise AdjudicationImportError(
            f"Could not read completed adjudication CSV: {path}"
        ) from exc
    if not rows:
        raise AdjudicationImportError("Completed adjudication CSV contains no resolutions.")
    return rows


def _record_from_row(
    row: Mapping[str, str],
    *,
    row_number: int,
    queue_item: AdjudicationQueueItem,
    pair: ReviewerPair,
    adjudication_id: str,
    reviewer_a_id: str,
    reviewer_b_id: str,
) -> AdjudicationRecord:
    adjudicator_id = _required_text(
        row["adjudicator_id"], f"row {row_number} adjudicator_id"
    )
    if adjudicator_id in {reviewer_a_id, reviewer_b_id}:
        raise AdjudicationImportError(
            f"Row {row_number} adjudicator must differ from reviewers A and B."
        )
    try:
        outcome = AdjudicationOutcome(row["outcome"])
    except ValueError as exc:
        allowed = ", ".join(value.value for value in AdjudicationOutcome)
        raise AdjudicationImportError(
            f"Row {row_number} outcome must be one of: {allowed}."
        ) from exc
    reasons = _parse_reason_codes(row["resolution_reason_codes"], row_number)
    final_class = row["final_primary_class"] or None
    final_geometry = row["final_geometry"] or None
    _validate_outcome_interchange(
        outcome,
        final_primary_class=final_class,
        final_geometry=final_geometry,
        row_number=row_number,
    )
    resolved_at = _parse_timestamp(row["resolved_at_utc"], row_number, "resolved_at_utc")
    locked_at = _parse_timestamp(row["locked_at_utc"], row_number, "locked_at_utc")
    try:
        return build_adjudication_record(
            queue_item,
            pair,
            adjudication_id=adjudication_id,
            adjudicator_id=adjudicator_id,
            outcome=outcome,
            final_primary_class=final_class,
            final_geometry=final_geometry,
            ambiguity_reason_codes=reasons,
            notes=row["notes"],
            protocol_version=_required_text(
                row["protocol_version"], f"row {row_number} protocol_version"
            ),
            resolved_at_utc=resolved_at,
            locked_at_utc=locked_at,
        )
    except AdjudicationError as exc:
        raise AdjudicationImportError(
            f"Invalid completed adjudication at row {row_number}: {exc}"
        ) from exc


def _validate_outcome_interchange(
    outcome: AdjudicationOutcome,
    *,
    final_primary_class: str | None,
    final_geometry: str | None,
    row_number: int,
) -> None:
    if outcome in {AdjudicationOutcome.ACCEPT_A, AdjudicationOutcome.ACCEPT_B}:
        if final_primary_class is not None or final_geometry is not None:
            raise AdjudicationImportError(
                f"Row {row_number} {outcome.value} must leave final class and geometry "
                "blank; both are copied from the selected locked review."
            )
    elif outcome is AdjudicationOutcome.REDRAW:
        if final_primary_class is None or final_geometry is None:
            raise AdjudicationImportError(
                f"Row {row_number} redraw requires final_primary_class and final_geometry."
            )
    elif outcome in {
        AdjudicationOutcome.UNCERTAIN,
        AdjudicationOutcome.UNOBSERVABLE,
    }:
        if final_primary_class is not None:
            raise AdjudicationImportError(
                f"Row {row_number} {outcome.value} must leave final_primary_class blank; "
                "the canonical class is derived from the outcome."
            )
    elif final_primary_class is not None or final_geometry is not None:
        raise AdjudicationImportError(
            f"Row {row_number} reject must leave final class and geometry blank."
        )


def _parse_reason_codes(value: str, row_number: int) -> tuple[str, ...]:
    reasons = tuple(part.strip() for part in value.split(";") if part.strip())
    if not reasons:
        raise AdjudicationImportError(
            f"Row {row_number} resolution_reason_codes must not be blank."
        )
    if len(reasons) != len(set(reasons)):
        raise AdjudicationImportError(
            f"Row {row_number} resolution_reason_codes contains duplicates."
        )
    unknown = sorted(set(reasons) - RESOLUTION_REASON_CODES)
    if unknown:
        raise AdjudicationImportError(
            f"Row {row_number} has unknown resolution reason codes: {unknown}."
        )
    return reasons


def _pair_index(pairs: Sequence[ReviewerPair]) -> dict[tuple[str, str], ReviewerPair]:
    result: dict[tuple[str, str], ReviewerPair] = {}
    for pair in pairs:
        key = (pair.event_id, pair.query_region_id)
        if key in result:
            raise AdjudicationImportError(
                f"Duplicate locked reviewer pair for {pair.event_id}/{pair.query_region_id}."
            )
        result[key] = pair
    return result


def _source_annotation_hashes(
    queue_items: Sequence[AdjudicationQueueItem],
) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in queue_items:
        for annotation_id, digest in (
            (item.reviewer_a_annotation_id, item.reviewer_a_sha256),
            (item.reviewer_b_annotation_id, item.reviewer_b_sha256),
        ):
            previous = result.setdefault(annotation_id, digest)
            if previous != digest:
                raise AdjudicationImportError(
                    f"Annotation id {annotation_id} has conflicting source hashes."
                )
    return result


def _existing_file(value: str | Path, label: str) -> Path:
    path = Path(value)
    if not path.is_file():
        raise AdjudicationImportError(f"{label} does not exist or is not a file: {path}")
    return path


def _require_distinct_paths(*paths: Path) -> None:
    resolved = [path.resolve() for path in paths]
    if len(resolved) != len(set(resolved)):
        raise AdjudicationImportError(
            "Input, log, and receipt paths must all be distinct."
        )


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AdjudicationImportError(f"{field_name} must not be blank.")
    return value.strip()


def _parse_timestamp(value: str, row_number: int, field_name: str) -> datetime:
    text = _required_text(value, f"row {row_number} {field_name}")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AdjudicationImportError(
            f"Row {row_number} {field_name} is not an ISO-8601 timestamp."
        ) from exc
    return _as_utc(parsed, f"row {row_number} {field_name}")


def _as_utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise AdjudicationImportError(f"{field_name} must be timezone-aware.")
    return value.astimezone(timezone.utc)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
