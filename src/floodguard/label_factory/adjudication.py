"""Immutable adjudication records for double-blind flood-label review.

Adjudication is deliberately separate from the two source annotations.  Raw
reviewer submissions are never rewritten: a resolution names and hashes both
locked inputs, records one explicit outcome, and is appended to a tamper-
evident JSON Lines log.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from floodguard.label_factory.annotations import (
    AnnotationRecord,
    LabelClass,
    ReviewerConfidence,
    annotation_content_sha256,
    coerce_label_class,
    validate_blinding,
)


class AdjudicationError(ValueError):
    """Raised when a queue or immutable resolution violates the contract."""


class AdjudicationOutcome(str, Enum):
    """The six protocol-approved adjudication outcomes."""

    ACCEPT_A = "accept_a"
    ACCEPT_B = "accept_b"
    REDRAW = "redraw"
    UNCERTAIN = "uncertain"
    UNOBSERVABLE = "unobservable"
    REJECT = "reject"


class AdjudicationStatus(str, Enum):
    """Queue state.  A resolution record closes exactly one open item."""

    OPEN = "open"
    RESOLVED = "resolved"


QUEUE_REASON_CODES: frozenset[str] = frozenset(
    {
        "class_disagreement",
        "geometry_disagreement",
        "reviewed_extent_disagreement",
        "low_confidence_a",
        "low_confidence_b",
        "uncertain_a",
        "uncertain_b",
        "unobservable_a",
        "unobservable_b",
    }
)


@dataclass(frozen=True, slots=True)
class ReviewerPair:
    """Latest locked submissions from two explicitly named reviewers."""

    event_id: str
    tile_id: str
    query_region_id: str
    reviewer_a: AnnotationRecord
    reviewer_b: AnnotationRecord

    def __post_init__(self) -> None:
        for field_name in ("event_id", "tile_id", "query_region_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise AdjudicationError(f"{field_name} must not be blank.")
            object.__setattr__(self, field_name, value.strip())
        _validate_source_annotation(self.reviewer_a, "reviewer_a")
        _validate_source_annotation(self.reviewer_b, "reviewer_b")
        if self.reviewer_a.reviewer_id == self.reviewer_b.reviewer_id:
            raise AdjudicationError("Reviewer A and reviewer B must be different people.")
        for record in (self.reviewer_a, self.reviewer_b):
            observed = (record.event_id, record.tile_id, record.query_region_id)
            expected = (self.event_id, self.tile_id, self.query_region_id)
            if observed != expected:
                raise AdjudicationError(
                    "Paired annotations must have identical event, tile, and query ids."
                )
        if self.reviewer_a.annotation_id == self.reviewer_b.annotation_id:
            raise AdjudicationError("Paired annotations must have distinct annotation ids.")


@dataclass(frozen=True, slots=True)
class AdjudicationQueueItem:
    """One explicit, machine-generated request for human adjudication."""

    queue_id: str
    event_id: str
    tile_id: str
    query_region_id: str
    reviewer_a_annotation_id: str
    reviewer_b_annotation_id: str
    reviewer_a_sha256: str
    reviewer_b_sha256: str
    reason_codes: tuple[str, ...]
    created_at_utc: datetime
    status: AdjudicationStatus = AdjudicationStatus.OPEN

    def __post_init__(self) -> None:
        for field_name in (
            "queue_id",
            "event_id",
            "tile_id",
            "query_region_id",
            "reviewer_a_annotation_id",
            "reviewer_b_annotation_id",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise AdjudicationError(f"{field_name} must not be blank.")
            object.__setattr__(self, field_name, value.strip())
        _require_sha256(self.reviewer_a_sha256, "reviewer_a_sha256")
        _require_sha256(self.reviewer_b_sha256, "reviewer_b_sha256")
        reasons = _unique_nonblank(self.reason_codes, "reason_codes")
        unknown = sorted(set(reasons) - QUEUE_REASON_CODES)
        if unknown:
            raise AdjudicationError(
                "Unknown adjudication reason codes: " + ", ".join(unknown)
            )
        if not reasons:
            raise AdjudicationError(
                "An adjudication queue item requires at least one explicit reason."
            )
        object.__setattr__(self, "reason_codes", reasons)
        object.__setattr__(self, "created_at_utc", _as_utc(self.created_at_utc, "created_at_utc"))
        object.__setattr__(self, "status", _coerce_enum(self.status, AdjudicationStatus))
        if self.status is not AdjudicationStatus.OPEN:
            raise AdjudicationError("New adjudication queue items must have status='open'.")

    def to_dict(self) -> dict[str, Any]:
        """Return stable CSV/JSON-compatible fields."""

        return {
            "queue_id": self.queue_id,
            "event_id": self.event_id,
            "tile_id": self.tile_id,
            "query_region_id": self.query_region_id,
            "reviewer_a_annotation_id": self.reviewer_a_annotation_id,
            "reviewer_b_annotation_id": self.reviewer_b_annotation_id,
            "reviewer_a_sha256": self.reviewer_a_sha256,
            "reviewer_b_sha256": self.reviewer_b_sha256,
            "reason_codes": ";".join(self.reason_codes),
            "created_at_utc": _iso_utc(self.created_at_utc),
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AdjudicationQueueItem:
        """Parse a queue item written by :meth:`to_dict`."""

        try:
            reasons = payload["reason_codes"]
            return cls(
                queue_id=payload["queue_id"],
                event_id=payload["event_id"],
                tile_id=payload["tile_id"],
                query_region_id=payload["query_region_id"],
                reviewer_a_annotation_id=payload["reviewer_a_annotation_id"],
                reviewer_b_annotation_id=payload["reviewer_b_annotation_id"],
                reviewer_a_sha256=payload["reviewer_a_sha256"],
                reviewer_b_sha256=payload["reviewer_b_sha256"],
                reason_codes=(
                    tuple(value.strip() for value in reasons.split(";") if value.strip())
                    if isinstance(reasons, str)
                    else tuple(reasons)
                ),
                created_at_utc=_parse_timestamp(payload["created_at_utc"]),
                status=_coerce_enum(payload.get("status", "open"), AdjudicationStatus),
            )
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, AdjudicationError):
                raise
            raise AdjudicationError(f"Invalid adjudication queue item: {exc}") from exc


@dataclass(frozen=True, slots=True)
class AdjudicationRecord:
    """One immutable human resolution that references two locked reviews."""

    adjudication_id: str
    queue_id: str
    event_id: str
    tile_id: str
    query_region_id: str
    reviewer_a_annotation_id: str
    reviewer_b_annotation_id: str
    reviewer_a_sha256: str
    reviewer_b_sha256: str
    adjudicator_id: str
    outcome: AdjudicationOutcome
    final_primary_class: LabelClass | None
    final_geometry: str | None
    ambiguity_reason_codes: tuple[str, ...]
    notes: str
    protocol_version: str
    resolved_at_utc: datetime
    locked_at_utc: datetime

    def __post_init__(self) -> None:
        for field_name in (
            "adjudication_id",
            "queue_id",
            "event_id",
            "tile_id",
            "query_region_id",
            "reviewer_a_annotation_id",
            "reviewer_b_annotation_id",
            "adjudicator_id",
            "protocol_version",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise AdjudicationError(f"{field_name} must not be blank.")
            object.__setattr__(self, field_name, value.strip())
        if self.reviewer_a_annotation_id == self.reviewer_b_annotation_id:
            raise AdjudicationError("Adjudication must reference two distinct annotations.")
        _require_sha256(self.reviewer_a_sha256, "reviewer_a_sha256")
        _require_sha256(self.reviewer_b_sha256, "reviewer_b_sha256")
        object.__setattr__(self, "outcome", _coerce_enum(self.outcome, AdjudicationOutcome))
        if self.final_primary_class is not None:
            object.__setattr__(
                self,
                "final_primary_class",
                coerce_label_class(self.final_primary_class),
            )
        reasons = _unique_nonblank(self.ambiguity_reason_codes, "ambiguity_reason_codes")
        object.__setattr__(self, "ambiguity_reason_codes", reasons)
        if not reasons:
            raise AdjudicationError(
                "Every adjudication requires at least one explicit resolution reason code."
            )
        if not isinstance(self.notes, str):
            raise AdjudicationError("notes must be a string (it may be blank).")
        object.__setattr__(self, "notes", self.notes.strip())
        if self.final_geometry is not None:
            if not isinstance(self.final_geometry, str) or not self.final_geometry.strip():
                raise AdjudicationError("final_geometry must be non-blank when supplied.")
            object.__setattr__(self, "final_geometry", self.final_geometry.strip())
        resolved = _as_utc(self.resolved_at_utc, "resolved_at_utc")
        locked = _as_utc(self.locked_at_utc, "locked_at_utc")
        if locked < resolved:
            raise AdjudicationError("locked_at_utc must not precede resolved_at_utc.")
        object.__setattr__(self, "resolved_at_utc", resolved)
        object.__setattr__(self, "locked_at_utc", locked)
        _validate_outcome_fields(self)

    @property
    def resolution_reason_codes(self) -> tuple[str, ...]:
        """Return adjudicator reason codes (stored under the legacy field name)."""

        return self.ambiguity_reason_codes

    def to_dict(self) -> dict[str, Any]:
        """Serialize the immutable resolution deterministically."""

        return {
            "adjudication_id": self.adjudication_id,
            "queue_id": self.queue_id,
            "event_id": self.event_id,
            "tile_id": self.tile_id,
            "query_region_id": self.query_region_id,
            "reviewer_a_annotation_id": self.reviewer_a_annotation_id,
            "reviewer_b_annotation_id": self.reviewer_b_annotation_id,
            "reviewer_a_sha256": self.reviewer_a_sha256,
            "reviewer_b_sha256": self.reviewer_b_sha256,
            "adjudicator_id": self.adjudicator_id,
            "outcome": self.outcome.value,
            "final_primary_class": (
                int(self.final_primary_class) if self.final_primary_class is not None else None
            ),
            "final_geometry": self.final_geometry,
            "ambiguity_reason_codes": list(self.ambiguity_reason_codes),
            "resolution_reason_codes": list(self.ambiguity_reason_codes),
            "notes": self.notes,
            "protocol_version": self.protocol_version,
            "resolved_at_utc": _iso_utc(self.resolved_at_utc),
            "locked_at_utc": _iso_utc(self.locked_at_utc),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AdjudicationRecord:
        """Parse and validate a serialized resolution."""

        try:
            final_class = payload.get("final_primary_class")
            legacy_reasons = tuple(payload.get("ambiguity_reason_codes", ()))
            resolution_reasons = tuple(
                payload.get("resolution_reason_codes", legacy_reasons)
            )
            if (
                "ambiguity_reason_codes" in payload
                and "resolution_reason_codes" in payload
                and legacy_reasons != resolution_reasons
            ):
                raise AdjudicationError(
                    "Serialized adjudication reason-code fields disagree."
                )
            return cls(
                adjudication_id=payload["adjudication_id"],
                queue_id=payload["queue_id"],
                event_id=payload["event_id"],
                tile_id=payload["tile_id"],
                query_region_id=payload["query_region_id"],
                reviewer_a_annotation_id=payload["reviewer_a_annotation_id"],
                reviewer_b_annotation_id=payload["reviewer_b_annotation_id"],
                reviewer_a_sha256=payload["reviewer_a_sha256"],
                reviewer_b_sha256=payload["reviewer_b_sha256"],
                adjudicator_id=payload["adjudicator_id"],
                outcome=_coerce_enum(payload["outcome"], AdjudicationOutcome),
                final_primary_class=(
                    None if final_class is None or final_class == "" else coerce_label_class(final_class)
                ),
                final_geometry=payload.get("final_geometry"),
                ambiguity_reason_codes=resolution_reasons,
                notes=payload.get("notes", ""),
                protocol_version=payload["protocol_version"],
                resolved_at_utc=_parse_timestamp(payload["resolved_at_utc"]),
                locked_at_utc=_parse_timestamp(payload["locked_at_utc"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, AdjudicationError):
                raise
            raise AdjudicationError(f"Invalid adjudication record: {exc}") from exc


def pair_locked_annotations(
    records: Sequence[AnnotationRecord],
    *,
    reviewer_a_id: str,
    reviewer_b_id: str,
) -> tuple[ReviewerPair, ...]:
    """Pair each query's latest locked A/B revision and fail on incomplete pairs.

    Reviewer identities are explicit arguments; the function never guesses which
    two people should be treated as A and B.
    """

    reviewer_a_id = _required_text(reviewer_a_id, "reviewer_a_id")
    reviewer_b_id = _required_text(reviewer_b_id, "reviewer_b_id")
    if reviewer_a_id == reviewer_b_id:
        raise AdjudicationError("reviewer_a_id and reviewer_b_id must differ.")
    relevant = [
        record
        for record in records
        if record.reviewer_id in {reviewer_a_id, reviewer_b_id}
    ]
    if not relevant:
        raise AdjudicationError("No annotations exist for the named reviewers.")
    latest: dict[tuple[str, str, str], AnnotationRecord] = {}
    query_keys: set[tuple[str, str]] = set()
    for record in relevant:
        _validate_source_annotation(record, "annotation")
        query_key = (record.event_id, record.query_region_id)
        query_keys.add(query_key)
        key = (record.event_id, record.query_region_id, record.reviewer_id)
        previous = latest.get(key)
        if previous is None or record.reviewer_revision > previous.reviewer_revision:
            latest[key] = record

    pairs: list[ReviewerPair] = []
    for event_id, query_region_id in sorted(query_keys):
        a = latest.get((event_id, query_region_id, reviewer_a_id))
        b = latest.get((event_id, query_region_id, reviewer_b_id))
        if a is None or b is None:
            missing = reviewer_a_id if a is None else reviewer_b_id
            raise AdjudicationError(
                f"Query {event_id}/{query_region_id} lacks a locked review from {missing}."
            )
        if a.tile_id != b.tile_id:
            raise AdjudicationError(
                f"Query {event_id}/{query_region_id} has conflicting tile ids."
            )
        pairs.append(
            ReviewerPair(
                event_id=event_id,
                tile_id=a.tile_id,
                query_region_id=query_region_id,
                reviewer_a=a,
                reviewer_b=b,
            )
        )
    return tuple(pairs)


def adjudication_reasons(pair: ReviewerPair) -> tuple[str, ...]:
    """Return protocol reasons that require a third human decision."""

    reasons: list[str] = []
    a = pair.reviewer_a
    b = pair.reviewer_b
    if a.primary_class is not b.primary_class:
        reasons.append("class_disagreement")
    if _normalized_geometry(a.geometry) != _normalized_geometry(b.geometry):
        reasons.append("geometry_disagreement")
    if _normalized_geometry(a.reviewed_extent) != _normalized_geometry(b.reviewed_extent):
        reasons.append("reviewed_extent_disagreement")
    if a.confidence is ReviewerConfidence.LOW:
        reasons.append("low_confidence_a")
    if b.confidence is ReviewerConfidence.LOW:
        reasons.append("low_confidence_b")
    if a.primary_class is LabelClass.UNCERTAIN_WATER_CHANGE:
        reasons.append("uncertain_a")
    if b.primary_class is LabelClass.UNCERTAIN_WATER_CHANGE:
        reasons.append("uncertain_b")
    if a.primary_class is LabelClass.UNOBSERVABLE_OR_ARTIFACT:
        reasons.append("unobservable_a")
    if b.primary_class is LabelClass.UNOBSERVABLE_OR_ARTIFACT:
        reasons.append("unobservable_b")
    return tuple(reasons)


def build_adjudication_queue(
    pairs: Sequence[ReviewerPair],
    *,
    created_at_utc: datetime,
    queue_prefix: str = "ADJQ",
) -> tuple[AdjudicationQueueItem, ...]:
    """Build queue items only for explicit disagreements or ambiguity triggers."""

    created = _as_utc(created_at_utc, "created_at_utc")
    prefix = _required_text(queue_prefix, "queue_prefix")
    items: list[AdjudicationQueueItem] = []
    seen_queries: set[tuple[str, str]] = set()
    for pair in pairs:
        query_key = (pair.event_id, pair.query_region_id)
        if query_key in seen_queries:
            raise AdjudicationError(f"Duplicate reviewer pair: {pair.event_id}/{pair.query_region_id}")
        seen_queries.add(query_key)
        reasons = adjudication_reasons(pair)
        if not reasons:
            continue
        stable = hashlib.sha256(
            (
                f"{pair.event_id}\0{pair.query_region_id}\0"
                f"{pair.reviewer_a.annotation_id}\0{pair.reviewer_b.annotation_id}"
            ).encode("utf-8")
        ).hexdigest()[:16]
        items.append(
            AdjudicationQueueItem(
                queue_id=f"{prefix}-{stable}",
                event_id=pair.event_id,
                tile_id=pair.tile_id,
                query_region_id=pair.query_region_id,
                reviewer_a_annotation_id=pair.reviewer_a.annotation_id,
                reviewer_b_annotation_id=pair.reviewer_b.annotation_id,
                reviewer_a_sha256=annotation_content_sha256(pair.reviewer_a),
                reviewer_b_sha256=annotation_content_sha256(pair.reviewer_b),
                reason_codes=reasons,
                created_at_utc=created,
            )
        )
    return tuple(items)


def build_adjudication_record(
    queue_item: AdjudicationQueueItem,
    pair: ReviewerPair,
    *,
    adjudication_id: str,
    adjudicator_id: str,
    outcome: AdjudicationOutcome | str,
    resolved_at_utc: datetime,
    locked_at_utc: datetime,
    protocol_version: str,
    final_primary_class: LabelClass | int | str | None = None,
    final_geometry: str | None = None,
    ambiguity_reason_codes: Iterable[str] = (),
    notes: str = "",
) -> AdjudicationRecord:
    """Resolve one queue item without changing either source annotation."""

    validate_queue_item_sources(queue_item, pair)
    parsed_outcome = _coerce_enum(outcome, AdjudicationOutcome)
    resolved_class: LabelClass | None
    resolved_geometry = final_geometry
    if parsed_outcome is AdjudicationOutcome.ACCEPT_A:
        resolved_class = pair.reviewer_a.primary_class
        resolved_geometry = pair.reviewer_a.geometry
    elif parsed_outcome is AdjudicationOutcome.ACCEPT_B:
        resolved_class = pair.reviewer_b.primary_class
        resolved_geometry = pair.reviewer_b.geometry
    elif parsed_outcome is AdjudicationOutcome.UNCERTAIN:
        resolved_class = LabelClass.UNCERTAIN_WATER_CHANGE
    elif parsed_outcome is AdjudicationOutcome.UNOBSERVABLE:
        resolved_class = LabelClass.UNOBSERVABLE_OR_ARTIFACT
    elif parsed_outcome is AdjudicationOutcome.REJECT:
        resolved_class = None
        resolved_geometry = None
    else:
        resolved_class = (
            coerce_label_class(final_primary_class)
            if final_primary_class is not None
            else None
        )
    if final_primary_class is not None and parsed_outcome is not AdjudicationOutcome.REDRAW:
        supplied = coerce_label_class(final_primary_class)
        if supplied is not resolved_class:
            raise AdjudicationError(
                "final_primary_class conflicts with the selected adjudication outcome."
            )
    return AdjudicationRecord(
        adjudication_id=adjudication_id,
        queue_id=queue_item.queue_id,
        event_id=queue_item.event_id,
        tile_id=queue_item.tile_id,
        query_region_id=queue_item.query_region_id,
        reviewer_a_annotation_id=queue_item.reviewer_a_annotation_id,
        reviewer_b_annotation_id=queue_item.reviewer_b_annotation_id,
        reviewer_a_sha256=queue_item.reviewer_a_sha256,
        reviewer_b_sha256=queue_item.reviewer_b_sha256,
        adjudicator_id=adjudicator_id,
        outcome=parsed_outcome,
        final_primary_class=resolved_class,
        final_geometry=resolved_geometry,
        ambiguity_reason_codes=tuple(ambiguity_reason_codes),
        notes=notes,
        protocol_version=protocol_version,
        resolved_at_utc=resolved_at_utc,
        locked_at_utc=locked_at_utc,
    )


def validate_queue_item_sources(
    queue_item: AdjudicationQueueItem,
    pair: ReviewerPair,
) -> None:
    """Verify queue identity and hashes against the two immutable reviews."""

    expected = (
        pair.event_id,
        pair.tile_id,
        pair.query_region_id,
        pair.reviewer_a.annotation_id,
        pair.reviewer_b.annotation_id,
        annotation_content_sha256(pair.reviewer_a),
        annotation_content_sha256(pair.reviewer_b),
    )
    observed = (
        queue_item.event_id,
        queue_item.tile_id,
        queue_item.query_region_id,
        queue_item.reviewer_a_annotation_id,
        queue_item.reviewer_b_annotation_id,
        queue_item.reviewer_a_sha256,
        queue_item.reviewer_b_sha256,
    )
    if observed != expected:
        raise AdjudicationError(
            f"Queue item {queue_item.queue_id} does not match its source annotations."
        )


def append_adjudication_record(path: str | Path, record: AdjudicationRecord) -> str:
    """Append one locked resolution to a hash-chained log."""

    return append_adjudication_records(path, (record,))[0]


def append_adjudication_records(
    path: str | Path,
    records: Sequence[AdjudicationRecord],
) -> tuple[str, ...]:
    """Append a fully validated resolution batch in one durable write.

    Validation happens before the file is opened for append, so a duplicate
    adjudication id or a second resolution for one queue item cannot leave a
    partly appended batch.  The returned hashes are the hash-chain envelope
    digests in input order.
    """

    target = Path(path)
    existing = load_adjudication_log(target) if target.exists() else []
    batch = tuple(records)
    if not batch:
        raise AdjudicationError("Adjudication append batch must not be empty.")
    if any(not isinstance(record, AdjudicationRecord) for record in batch):
        raise AdjudicationError("Every append-batch item must be an AdjudicationRecord.")
    existing_ids = {item.adjudication_id for item in existing}
    existing_queue_ids = {item.queue_id for item in existing}
    batch_ids: set[str] = set()
    batch_queue_ids: set[str] = set()
    for record in batch:
        if record.adjudication_id in existing_ids or record.adjudication_id in batch_ids:
            raise AdjudicationError(
                "adjudication_id already exists and cannot be overwritten: "
                f"{record.adjudication_id}"
            )
        if record.queue_id in existing_queue_ids or record.queue_id in batch_queue_ids:
            raise AdjudicationError(
                "Queue item is already resolved and cannot be resolved twice: "
                f"{record.queue_id}"
            )
        batch_ids.add(record.adjudication_id)
        batch_queue_ids.add(record.queue_id)

    previous_hash = _last_envelope_hash(target) if target.exists() else None
    hashes: list[str] = []
    encoded_records: list[bytes] = []
    for record in batch:
        unsigned = {"previous_record_sha256": previous_hash, "record": record.to_dict()}
        record_hash = _sha256_json(unsigned)
        envelope = {**unsigned, "record_sha256": record_hash}
        encoded_records.append((_canonical_json(envelope) + "\n").encode("utf-8"))
        hashes.append(record_hash)
        previous_hash = record_hash
    encoded = b"".join(encoded_records)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(target, os.O_APPEND | os.O_CREAT | os.O_WRONLY)
    try:
        _write_all(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return tuple(hashes)


def load_adjudication_log(path: str | Path) -> list[AdjudicationRecord]:
    """Load and cryptographically verify an immutable resolution log."""

    source = Path(path)
    if not source.exists():
        return []
    records: list[AdjudicationRecord] = []
    seen_ids: set[str] = set()
    seen_queue_ids: set[str] = set()
    expected_previous: str | None = None
    for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            raise AdjudicationError(f"Blank line in adjudication log at line {line_number}.")
        try:
            envelope = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AdjudicationError(
                f"Invalid adjudication JSON at line {line_number}."
            ) from exc
        if not isinstance(envelope, Mapping):
            raise AdjudicationError(
                f"Adjudication log line {line_number} must be a JSON object."
            )
        if envelope.get("previous_record_sha256") != expected_previous:
            raise AdjudicationError(
                f"Adjudication hash-chain break at line {line_number}."
            )
        unsigned = {
            "previous_record_sha256": envelope.get("previous_record_sha256"),
            "record": envelope.get("record"),
        }
        observed_hash = envelope.get("record_sha256")
        if observed_hash != _sha256_json(unsigned):
            raise AdjudicationError(
                f"Adjudication content hash mismatch at line {line_number}."
            )
        if not isinstance(envelope.get("record"), Mapping):
            raise AdjudicationError(
                f"Adjudication record at line {line_number} must be a JSON object."
            )
        record = AdjudicationRecord.from_dict(envelope["record"])
        if record.adjudication_id in seen_ids:
            raise AdjudicationError(
                f"Duplicate adjudication_id in log: {record.adjudication_id}"
            )
        if record.queue_id in seen_queue_ids:
            raise AdjudicationError(f"Queue item resolved twice: {record.queue_id}")
        seen_ids.add(record.adjudication_id)
        seen_queue_ids.add(record.queue_id)
        records.append(record)
        expected_previous = str(observed_hash)
    return records


def unresolved_queue_items(
    queue_items: Sequence[AdjudicationQueueItem],
    resolutions: Sequence[AdjudicationRecord],
) -> tuple[AdjudicationQueueItem, ...]:
    """Return open items after validating one-to-one resolution lineage."""

    queue_by_id = _unique_by_id(queue_items, "queue_id", "queue item")
    resolution_by_queue = _unique_by_id(resolutions, "queue_id", "resolution")
    extras = sorted(set(resolution_by_queue) - set(queue_by_id))
    if extras:
        raise AdjudicationError(
            "Adjudication resolutions reference unknown queue ids: " + ", ".join(extras)
        )
    for queue_id, resolution in resolution_by_queue.items():
        queue = queue_by_id[queue_id]
        queue_identity = (
            queue.event_id,
            queue.tile_id,
            queue.query_region_id,
            queue.reviewer_a_annotation_id,
            queue.reviewer_b_annotation_id,
            queue.reviewer_a_sha256,
            queue.reviewer_b_sha256,
        )
        resolution_identity = (
            resolution.event_id,
            resolution.tile_id,
            resolution.query_region_id,
            resolution.reviewer_a_annotation_id,
            resolution.reviewer_b_annotation_id,
            resolution.reviewer_a_sha256,
            resolution.reviewer_b_sha256,
        )
        if resolution_identity != queue_identity:
            raise AdjudicationError(
                f"Resolution {resolution.adjudication_id} does not match queue item {queue_id}."
            )
    return tuple(queue_by_id[key] for key in sorted(set(queue_by_id) - set(resolution_by_queue)))


def _validate_source_annotation(record: AnnotationRecord, label: str) -> None:
    if not isinstance(record, AnnotationRecord):
        raise AdjudicationError(f"{label} must be an AnnotationRecord.")
    if not record.is_locked or not record.review_complete:
        raise AdjudicationError(f"{label} must be locked and complete.")
    try:
        validate_blinding(record)
    except ValueError as exc:
        raise AdjudicationError(f"{label} is not independently blinded: {exc}") from exc


def _validate_outcome_fields(record: AdjudicationRecord) -> None:
    if record.outcome is AdjudicationOutcome.REJECT:
        if record.final_primary_class is not None or record.final_geometry is not None:
            raise AdjudicationError("A rejected query cannot carry a final class or geometry.")
        if not record.notes:
            raise AdjudicationError("A rejected query requires an explanatory note.")
        return
    if record.final_primary_class is None:
        raise AdjudicationError(
            f"Outcome {record.outcome.value} requires a final_primary_class."
        )
    if record.final_primary_class is LabelClass.UNREVIEWED:
        raise AdjudicationError("Adjudication cannot resolve a query to unreviewed.")
    if record.outcome is AdjudicationOutcome.UNCERTAIN:
        if record.final_primary_class is not LabelClass.UNCERTAIN_WATER_CHANGE:
            raise AdjudicationError("uncertain outcome must use uncertain_water_change.")
    if record.outcome is AdjudicationOutcome.UNOBSERVABLE:
        if record.final_primary_class is not LabelClass.UNOBSERVABLE_OR_ARTIFACT:
            raise AdjudicationError("unobservable outcome must use unobservable_or_artifact.")
    if record.outcome is AdjudicationOutcome.REDRAW and record.final_geometry is None:
        raise AdjudicationError("redraw outcome requires final_geometry.")


def _unique_by_id(items: Sequence[Any], field_name: str, label: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in items:
        value = getattr(item, field_name)
        if value in result:
            raise AdjudicationError(f"Duplicate {label} {field_name}: {value}")
        result[value] = item
    return result


def _normalized_geometry(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(value.strip().split()).upper()


def _unique_nonblank(values: Iterable[Any], field_name: str) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise AdjudicationError(f"{field_name} values must be non-blank strings.")
        text = value.strip()
        if text not in normalized:
            normalized.append(text)
    return tuple(normalized)


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AdjudicationError(f"{field_name} must not be blank.")
    return value.strip()


def _require_sha256(value: Any, field_name: str) -> None:
    if not isinstance(value, str) or len(value) != 64:
        raise AdjudicationError(f"{field_name} must be a lowercase SHA-256 digest.")
    if any(character not in "0123456789abcdef" for character in value):
        raise AdjudicationError(f"{field_name} must be a lowercase SHA-256 digest.")


def _coerce_enum(value: Any, enum_type: type[Enum]) -> Any:
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(value)
    except (ValueError, TypeError) as exc:
        raise AdjudicationError(f"Invalid {enum_type.__name__}: {value!r}.") from exc


def _as_utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise AdjudicationError(f"{field_name} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise AdjudicationError(f"{field_name} must be timezone-aware.")
    return value.astimezone(timezone.utc)


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise AdjudicationError("Timestamp must not be blank.")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise AdjudicationError(f"Invalid timestamp: {value!r}.") from exc
    return _as_utc(parsed, "timestamp")


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _last_envelope_hash(path: Path) -> str | None:
    last: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            last = json.loads(line).get("record_sha256")
    return last


def _write_all(descriptor: int, data: bytes) -> None:
    view = memoryview(data)
    written = 0
    while written < len(view):
        count = os.write(descriptor, view[written:])
        if count <= 0:
            raise OSError("Could not append complete adjudication record.")
        written += count
