"""Immutable reviewer annotations and safe binary-label derivation.

The label-factory annotation contract deliberately distinguishes reviewed dry
land from pixels that are uncertain, unobservable, or simply unreviewed.  The
latter states are never silently converted to negative training examples.

Reviewer submissions are represented by frozen records and can be persisted
to a hash-chained JSON Lines log.  Appending a new revision never mutates an
older submission, and loading the log verifies both record content and chain
lineage.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping

from floodguard.label_factory.contracts import FloodLabel


# Backward-friendly local name with one canonical taxonomy source of truth.
# ``FloodLabel`` is defined in contracts.py and shared by rasterisation,
# annotation, agreement, QA, and model-training code.
LabelClass = FloodLabel


class AnnotationValidationError(ValueError):
    """Raised when an annotation violates the review or persistence contract."""


class ReviewerConfidence(str, Enum):
    """Human confidence; this is not a model probability."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ReviewStage(str, Enum):
    """Independent human-review stage represented by a record."""

    PRIMARY = "primary"
    SECONDARY = "secondary"


AMBIGUITY_REASON_CODES: frozenset[str] = frozenset(
    {
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
        "optical_cloud_or_shadow",
        "cross_border_context",
        "other",
    }
)

BINARY_TARGET_BY_CLASS: Mapping[LabelClass, int] = {
    LabelClass.DRY_LAND: 0,
    LabelClass.TEMPORARY_FLOOD: 1,
    LabelClass.PERMANENT_OR_PREEXISTING_WATER: 0,
}

EXCLUDED_FROM_BINARY_TRAINING: frozenset[LabelClass] = frozenset(
    {
        LabelClass.UNCERTAIN_WATER_CHANGE,
        LabelClass.UNOBSERVABLE_OR_ARTIFACT,
        LabelClass.UNREVIEWED,
    }
)


@dataclass(frozen=True, slots=True)
class BinaryTargetResult:
    """Binary targets plus an explicit eligibility mask.

    ``targets`` has the same length and ordering as the source labels.  A
    ``None`` target is deliberately ineligible and must be filtered using
    ``eligible_indices`` before model fitting.
    """

    targets: tuple[int | None, ...]
    eligible_indices: tuple[int, ...]
    excluded_indices: tuple[int, ...]

    @property
    def eligible_targets(self) -> tuple[int, ...]:
        """Return only targets that are legal training examples."""

        return tuple(
            target
            for target in self.targets
            if target is not None
        )


@dataclass(frozen=True, slots=True)
class AnnotationRecord:
    """One immutable, blinded reviewer submission.

    Reviewed extent is stored as stable WKT. Geometry is either legacy
    single-part WKT or the canonical, versioned multipart JSON payload consumed
    by reviewer-annotation rasterization. Keeping these fields textual avoids
    mutable nested objects inside an otherwise frozen record and keeps the core
    package independent of a particular geospatial library.
    """

    annotation_id: str
    event_id: str
    tile_id: str
    query_region_id: str
    reviewer_id: str
    reviewer_revision: int
    primary_class: LabelClass
    confidence: ReviewerConfidence
    ambiguity_reason_codes: tuple[str, ...]
    evidence_layers_used: tuple[str, ...]
    review_complete: bool
    reviewed_extent: str
    geometry: str | None
    review_started_at: datetime
    review_finished_at: datetime
    protocol_version: str
    tool_version: str
    model_predictions_visible: bool
    other_reviewer_annotations_visible: bool
    created_at_utc: datetime
    locked_at_utc: datetime | None
    review_stage: ReviewStage = ReviewStage.PRIMARY
    supersedes_annotation_id: str | None = None
    source_timestamp: datetime | None = None
    assumptions: str = ""
    bundle_manifest_sha256: str | None = None
    context_manifest_sha256: str | None = None
    grid_contract_sha256: str | None = None
    source_registry_sha256: str | None = None

    def __post_init__(self) -> None:
        """Normalize immutable values and reject unsafe review records."""

        for field_name in (
            "annotation_id",
            "event_id",
            "tile_id",
            "query_region_id",
            "reviewer_id",
            "reviewed_extent",
            "protocol_version",
            "tool_version",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise AnnotationValidationError(f"{field_name} must not be blank.")
            object.__setattr__(self, field_name, value.strip())

        if isinstance(self.reviewer_revision, bool) or self.reviewer_revision < 1:
            raise AnnotationValidationError("reviewer_revision must be a positive integer.")

        object.__setattr__(self, "primary_class", coerce_label_class(self.primary_class))
        object.__setattr__(self, "confidence", _coerce_enum(self.confidence, ReviewerConfidence))
        object.__setattr__(self, "review_stage", _coerce_enum(self.review_stage, ReviewStage))

        reasons = tuple(_normalized_nonblank_strings(self.ambiguity_reason_codes))
        unknown_reasons = sorted(set(reasons) - AMBIGUITY_REASON_CODES)
        if unknown_reasons:
            raise AnnotationValidationError(
                "Unknown ambiguity_reason_codes: " + ", ".join(unknown_reasons)
            )
        if self.primary_class in {
            LabelClass.UNCERTAIN_WATER_CHANGE,
            LabelClass.UNOBSERVABLE_OR_ARTIFACT,
        } and not reasons:
            raise AnnotationValidationError(
                "Uncertain or unobservable annotations require an ambiguity reason."
            )
        object.__setattr__(self, "ambiguity_reason_codes", reasons)

        evidence = tuple(_normalized_nonblank_strings(self.evidence_layers_used))
        if not evidence:
            raise AnnotationValidationError("evidence_layers_used must not be empty.")
        object.__setattr__(self, "evidence_layers_used", evidence)

        if not isinstance(self.review_complete, bool):
            raise AnnotationValidationError("review_complete must be boolean.")
        if self.review_complete and self.primary_class is LabelClass.UNREVIEWED:
            raise AnnotationValidationError(
                "A complete review cannot retain the unreviewed label."
            )

        if self.geometry is not None:
            if not isinstance(self.geometry, str) or not self.geometry.strip():
                raise AnnotationValidationError("geometry must be non-blank when supplied.")
            object.__setattr__(self, "geometry", self.geometry.strip())

        started = _as_utc(self.review_started_at, "review_started_at")
        finished = _as_utc(self.review_finished_at, "review_finished_at")
        created = _as_utc(self.created_at_utc, "created_at_utc")
        locked = (
            _as_utc(self.locked_at_utc, "locked_at_utc")
            if self.locked_at_utc is not None
            else None
        )
        if finished < started:
            raise AnnotationValidationError(
                "review_finished_at must not precede review_started_at."
            )
        if locked is not None and locked < finished:
            raise AnnotationValidationError(
                "locked_at_utc must not precede review_finished_at."
            )
        if locked is not None and locked < created:
            raise AnnotationValidationError(
                "locked_at_utc must not precede created_at_utc."
            )
        object.__setattr__(self, "review_started_at", started)
        object.__setattr__(self, "review_finished_at", finished)
        object.__setattr__(self, "created_at_utc", created)
        object.__setattr__(self, "locked_at_utc", locked)

        supersedes = (
            self.supersedes_annotation_id.strip()
            if isinstance(self.supersedes_annotation_id, str)
            and self.supersedes_annotation_id.strip()
            else None
        )
        object.__setattr__(self, "supersedes_annotation_id", supersedes)
        if self.source_timestamp is not None:
            object.__setattr__(
                self,
                "source_timestamp",
                _as_utc(self.source_timestamp, "source_timestamp"),
            )
        if not isinstance(self.assumptions, str):
            raise AnnotationValidationError("assumptions must be text.")
        object.__setattr__(self, "assumptions", self.assumptions.strip())
        for field_name in (
            "bundle_manifest_sha256",
            "context_manifest_sha256",
            "grid_contract_sha256",
            "source_registry_sha256",
        ):
            value = getattr(self, field_name)
            if value is None:
                continue
            normalized = str(value).strip().lower()
            if len(normalized) != 64 or any(
                character not in "0123456789abcdef" for character in normalized
            ):
                raise AnnotationValidationError(
                    f"{field_name} must be a complete SHA-256 when supplied."
                )
            object.__setattr__(self, field_name, normalized)

        validate_blinding(self)

    @property
    def is_locked(self) -> bool:
        """Return whether the immutable submission has been formally locked."""

        return self.locked_at_utc is not None

    @property
    def is_binary_training_eligible(self) -> bool:
        """Return whether this record can contribute a binary training target."""

        return (
            self.is_locked
            and self.review_complete
            and self.primary_class in BINARY_TARGET_BY_CLASS
            and not self.model_predictions_visible
            and not self.other_reviewer_annotations_visible
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the record into a deterministic JSON-compatible mapping."""

        return {
            "annotation_id": self.annotation_id,
            "event_id": self.event_id,
            "tile_id": self.tile_id,
            "query_region_id": self.query_region_id,
            "reviewer_id": self.reviewer_id,
            "reviewer_revision": self.reviewer_revision,
            "primary_class": int(self.primary_class),
            "confidence": self.confidence.value,
            "ambiguity_reason_codes": list(self.ambiguity_reason_codes),
            "evidence_layers_used": list(self.evidence_layers_used),
            "review_complete": self.review_complete,
            "reviewed_extent": self.reviewed_extent,
            "geometry": self.geometry,
            "review_started_at": _iso_utc(self.review_started_at),
            "review_finished_at": _iso_utc(self.review_finished_at),
            "protocol_version": self.protocol_version,
            "tool_version": self.tool_version,
            "model_predictions_visible": self.model_predictions_visible,
            "other_reviewer_annotations_visible": self.other_reviewer_annotations_visible,
            "created_at_utc": _iso_utc(self.created_at_utc),
            "locked_at_utc": (
                _iso_utc(self.locked_at_utc) if self.locked_at_utc is not None else None
            ),
            "review_stage": self.review_stage.value,
            "supersedes_annotation_id": self.supersedes_annotation_id,
            "source_timestamp": (
                _iso_utc(self.source_timestamp)
                if self.source_timestamp is not None
                else None
            ),
            "assumptions": self.assumptions,
            "bundle_manifest_sha256": self.bundle_manifest_sha256,
            "context_manifest_sha256": self.context_manifest_sha256,
            "grid_contract_sha256": self.grid_contract_sha256,
            "source_registry_sha256": self.source_registry_sha256,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AnnotationRecord:
        """Build and validate a record from serialized values."""

        try:
            return cls(
                annotation_id=payload["annotation_id"],
                event_id=payload["event_id"],
                tile_id=payload["tile_id"],
                query_region_id=payload["query_region_id"],
                reviewer_id=payload["reviewer_id"],
                reviewer_revision=int(payload["reviewer_revision"]),
                primary_class=coerce_label_class(payload["primary_class"]),
                confidence=_coerce_enum(payload["confidence"], ReviewerConfidence),
                ambiguity_reason_codes=tuple(payload.get("ambiguity_reason_codes", ())),
                evidence_layers_used=tuple(payload.get("evidence_layers_used", ())),
                review_complete=payload["review_complete"],
                reviewed_extent=payload["reviewed_extent"],
                geometry=payload.get("geometry"),
                review_started_at=_parse_timestamp(payload["review_started_at"]),
                review_finished_at=_parse_timestamp(payload["review_finished_at"]),
                protocol_version=payload["protocol_version"],
                tool_version=payload["tool_version"],
                model_predictions_visible=payload["model_predictions_visible"],
                other_reviewer_annotations_visible=payload.get(
                    "other_reviewer_annotations_visible", False
                ),
                created_at_utc=_parse_timestamp(payload["created_at_utc"]),
                locked_at_utc=(
                    _parse_timestamp(payload["locked_at_utc"])
                    if payload.get("locked_at_utc")
                    else None
                ),
                review_stage=_coerce_enum(
                    payload.get("review_stage", ReviewStage.PRIMARY.value),
                    ReviewStage,
                ),
                supersedes_annotation_id=payload.get("supersedes_annotation_id"),
                source_timestamp=(
                    _parse_timestamp(payload["source_timestamp"])
                    if payload.get("source_timestamp")
                    else None
                ),
                assumptions=str(payload.get("assumptions", "")),
                bundle_manifest_sha256=payload.get("bundle_manifest_sha256"),
                context_manifest_sha256=payload.get("context_manifest_sha256"),
                grid_contract_sha256=payload.get("grid_contract_sha256"),
                source_registry_sha256=payload.get("source_registry_sha256"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, AnnotationValidationError):
                raise
            raise AnnotationValidationError(
                f"Invalid serialized annotation record: {exc}"
            ) from exc


def coerce_label_class(value: LabelClass | int | str) -> LabelClass:
    """Return a valid :class:`LabelClass` without accepting booleans."""

    if isinstance(value, bool):
        raise AnnotationValidationError("Boolean values are not label classes.")
    if isinstance(value, LabelClass):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise AnnotationValidationError("Label class must not be blank.")
        try:
            return LabelClass[stripped.upper()]
        except KeyError:
            try:
                return LabelClass(int(stripped))
            except (ValueError, TypeError) as exc:
                raise AnnotationValidationError(
                    f"Unknown label class: {value!r}."
                ) from exc
    try:
        return LabelClass(int(value))
    except (ValueError, TypeError) as exc:
        raise AnnotationValidationError(f"Unknown label class: {value!r}.") from exc


def derive_binary_target(label: LabelClass | int | str) -> int | None:
    """Map an explicit reviewed class to flood/non-flood or return ``None``.

    Only dry land, temporary flood, and permanent/pre-existing water are legal
    binary targets.  Uncertain, unobservable, and unreviewed values are excluded
    instead of being treated as dry land.
    """

    label_class = coerce_label_class(label)
    return BINARY_TARGET_BY_CLASS.get(label_class)


def derive_binary_targets(
    labels: Iterable[LabelClass | int | str],
) -> BinaryTargetResult:
    """Derive aligned binary targets with explicit eligible/excluded indices."""

    targets: list[int | None] = []
    eligible_indices: list[int] = []
    excluded_indices: list[int] = []
    for index, label in enumerate(labels):
        target = derive_binary_target(label)
        targets.append(target)
        if target is None:
            excluded_indices.append(index)
        else:
            eligible_indices.append(index)
    return BinaryTargetResult(
        targets=tuple(targets),
        eligible_indices=tuple(eligible_indices),
        excluded_indices=tuple(excluded_indices),
    )


def validate_blinding(record: AnnotationRecord) -> None:
    """Reject records influenced by model predictions or another reviewer."""

    if not isinstance(record.model_predictions_visible, bool):
        raise AnnotationValidationError("model_predictions_visible must be boolean.")
    if not isinstance(record.other_reviewer_annotations_visible, bool):
        raise AnnotationValidationError(
            "other_reviewer_annotations_visible must be boolean."
        )
    if record.model_predictions_visible:
        raise AnnotationValidationError(
            "Reviewer records must be blinded from model predictions."
        )
    if record.other_reviewer_annotations_visible:
        raise AnnotationValidationError(
            "Independent reviewers must be blinded from other reviewer annotations."
        )


def append_annotation_record(
    path: str | Path,
    record: AnnotationRecord,
) -> str:
    """Append a locked record to a tamper-evident JSONL log.

    The function rejects duplicate annotation IDs and requires reviewer
    revisions for the same event/query/reviewer to increase exactly by one.
    It returns the SHA-256 hash of the appended envelope.
    """

    target = Path(path)
    if not record.is_locked:
        raise AnnotationValidationError(
            "Only locked reviewer submissions may be appended to the immutable log."
        )
    existing = load_annotation_log(target) if target.exists() else []
    if any(item.annotation_id == record.annotation_id for item in existing):
        raise AnnotationValidationError(
            f"annotation_id already exists and cannot be overwritten: {record.annotation_id}"
        )

    same_series = [
        item
        for item in existing
        if (
            item.event_id,
            item.query_region_id,
            item.reviewer_id,
            item.review_stage,
        )
        == (
            record.event_id,
            record.query_region_id,
            record.reviewer_id,
            record.review_stage,
        )
    ]
    expected_revision = 1 + max(
        (item.reviewer_revision for item in same_series),
        default=0,
    )
    if record.reviewer_revision != expected_revision:
        raise AnnotationValidationError(
            "reviewer_revision must be append-only and sequential; "
            f"expected {expected_revision}, received {record.reviewer_revision}."
        )

    previous_hash = _last_envelope_hash(target) if target.exists() else None
    envelope_without_hash = {
        "previous_record_sha256": previous_hash,
        "record": record.to_dict(),
    }
    record_hash = _canonical_sha256(envelope_without_hash)
    envelope = {**envelope_without_hash, "record_sha256": record_hash}
    encoded = (_canonical_json(envelope) + "\n").encode("utf-8")

    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(target, os.O_APPEND | os.O_CREAT | os.O_WRONLY)
    try:
        _write_all(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return record_hash


def load_annotation_log(path: str | Path) -> list[AnnotationRecord]:
    """Load and verify every record in a hash-chained annotation log."""

    source = Path(path)
    if not source.exists():
        return []

    records: list[AnnotationRecord] = []
    seen_ids: set[str] = set()
    expected_previous: str | None = None
    for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            raise AnnotationValidationError(
                f"Blank line in annotation log at line {line_number}."
            )
        try:
            envelope = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AnnotationValidationError(
                f"Invalid annotation JSON at line {line_number}."
            ) from exc
        if not isinstance(envelope, dict):
            raise AnnotationValidationError(
                f"Annotation log line {line_number} must be a JSON object."
            )

        previous = envelope.get("previous_record_sha256")
        if previous != expected_previous:
            raise AnnotationValidationError(
                f"Annotation hash-chain break at line {line_number}."
            )
        supplied_hash = envelope.get("record_sha256")
        calculated_hash = _canonical_sha256(
            {
                "previous_record_sha256": previous,
                "record": envelope.get("record"),
            }
        )
        if supplied_hash != calculated_hash:
            raise AnnotationValidationError(
                f"Annotation content hash mismatch at line {line_number}."
            )
        if not isinstance(envelope.get("record"), dict):
            raise AnnotationValidationError(
                f"Annotation record at line {line_number} must be a JSON object."
            )
        record = AnnotationRecord.from_dict(envelope["record"])
        if not record.is_locked:
            raise AnnotationValidationError(
                f"Unlocked annotation found in immutable log at line {line_number}."
            )
        if record.annotation_id in seen_ids:
            raise AnnotationValidationError(
                f"Duplicate annotation_id in log: {record.annotation_id}"
            )
        seen_ids.add(record.annotation_id)
        records.append(record)
        expected_previous = supplied_hash

    _validate_revision_sequences(records)
    return records


def annotation_content_sha256(record: AnnotationRecord) -> str:
    """Return the canonical content hash of a reviewer record."""

    return _canonical_sha256(record.to_dict())


def _validate_revision_sequences(records: Iterable[AnnotationRecord]) -> None:
    revisions: dict[tuple[str, str, str, ReviewStage], list[int]] = {}
    for record in records:
        key = (
            record.event_id,
            record.query_region_id,
            record.reviewer_id,
            record.review_stage,
        )
        revisions.setdefault(key, []).append(record.reviewer_revision)
    for key, observed in revisions.items():
        expected = list(range(1, len(observed) + 1))
        if observed != expected:
            raise AnnotationValidationError(
                "Non-sequential reviewer revisions for "
                f"{key}: expected {expected}, observed {observed}."
            )


def _last_envelope_hash(path: Path) -> str | None:
    last_hash: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            payload = json.loads(line)
            last_hash = payload.get("record_sha256")
    return last_hash


def _as_utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise AnnotationValidationError(f"{field_name} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise AnnotationValidationError(f"{field_name} must be timezone-aware.")
    return value.astimezone(timezone.utc)


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise AnnotationValidationError("Serialized timestamp must not be blank.")
    normalized = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise AnnotationValidationError(f"Invalid timestamp: {value!r}.") from exc


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalized_nonblank_strings(values: Iterable[Any]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise AnnotationValidationError("List values must be non-blank strings.")
        text = value.strip()
        if text not in normalized:
            normalized.append(text)
    return normalized


def _coerce_enum(value: Any, enum_type: type[Enum]) -> Any:
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(value)
    except (ValueError, TypeError) as exc:
        raise AnnotationValidationError(
            f"Invalid {enum_type.__name__}: {value!r}."
        ) from exc


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _write_all(descriptor: int, data: bytes) -> None:
    view = memoryview(data)
    written = 0
    while written < len(view):
        count = os.write(descriptor, view[written:])
        if count <= 0:
            raise OSError("Could not append complete annotation record.")
        written += count
