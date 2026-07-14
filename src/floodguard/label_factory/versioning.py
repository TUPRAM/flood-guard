"""Immutable semantic versions and content hashes for reviewed labelsets.

Labelset manifests are written exactly once.  Each manifest binds the label
content, review sources, raster hashes, metadata, semantic contract, creation
time, and parent lineage into a canonical SHA-256 digest.  Major, minor, and
patch bumps have deliberately strict meanings so a metadata correction cannot
silently alter label pixels or review semantics.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Mapping


class LabelsetVersionError(ValueError):
    """Raised when labelset versions, hashes, or lineage are invalid."""


class ChangeKind(str, Enum):
    """Declared semantic meaning of a labelset release."""

    INITIAL = "initial"
    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"


@dataclass(frozen=True, order=True, slots=True)
class SemanticVersion:
    """Three-part semantic version without mutable prerelease semantics."""

    major: int
    minor: int
    patch: int

    def __post_init__(self) -> None:
        for field_name in ("major", "minor", "patch"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise LabelsetVersionError(
                    f"Semantic-version {field_name} must be a non-negative integer."
                )

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    @classmethod
    def parse(cls, value: SemanticVersion | str) -> SemanticVersion:
        """Parse ``0.1.0`` or ``v0.1.0`` into an immutable version."""

        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise LabelsetVersionError("Semantic version must be a string or object.")
        match = re.fullmatch(r"v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", value.strip())
        if match is None:
            raise LabelsetVersionError(
                f"Invalid semantic version {value!r}; expected MAJOR.MINOR.PATCH."
            )
        return cls(*(int(part) for part in match.groups()))

    def next_for(self, change_kind: ChangeKind | str) -> SemanticVersion:
        """Return the one legal successor for a declared change kind."""

        change = _coerce_change_kind(change_kind)
        if change is ChangeKind.MAJOR:
            return SemanticVersion(self.major + 1, 0, 0)
        if change is ChangeKind.MINOR:
            return SemanticVersion(self.major, self.minor + 1, 0)
        if change is ChangeKind.PATCH:
            return SemanticVersion(self.major, self.minor, self.patch + 1)
        raise LabelsetVersionError("An initial release has no parent version to bump.")


@dataclass(frozen=True, slots=True)
class LabelsetManifest:
    """Content-addressed, immutable labelset release manifest."""

    labelset_name: str
    version: SemanticVersion
    labelset_id: str
    change_kind: ChangeKind
    parent_labelset_id: str | None
    parent_manifest_sha256: str | None
    label_content_sha256: str
    metadata_sha256: str
    semantics_sha256: str
    source_annotation_ids: tuple[str, ...]
    raster_sha256_by_name: tuple[tuple[str, str], ...]
    created_at_utc: datetime
    manifest_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.labelset_name, str) or not re.fullmatch(
            r"[a-z0-9][a-z0-9_-]*",
            self.labelset_name,
        ):
            raise LabelsetVersionError(
                "labelset_name must use lowercase letters, digits, underscores, or hyphens."
            )
        if not isinstance(self.version, SemanticVersion):
            raise LabelsetVersionError("version must be a SemanticVersion.")
        if not isinstance(self.change_kind, ChangeKind):
            raise LabelsetVersionError("change_kind must be a ChangeKind.")
        expected_id = f"{self.labelset_name}_v{self.version}"
        if self.labelset_id != expected_id:
            raise LabelsetVersionError(
                f"labelset_id must be {expected_id!r}, received {self.labelset_id!r}."
            )

        if self.change_kind is ChangeKind.INITIAL:
            if self.parent_labelset_id is not None or self.parent_manifest_sha256 is not None:
                raise LabelsetVersionError(
                    "An initial labelset must not declare parent lineage."
                )
        elif not self.parent_labelset_id or not self.parent_manifest_sha256:
            raise LabelsetVersionError(
                "Non-initial labelsets require parent_labelset_id and parent hash."
            )

        for field_name in (
            "label_content_sha256",
            "metadata_sha256",
            "semantics_sha256",
            "manifest_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        if self.parent_manifest_sha256 is not None:
            _require_sha256(self.parent_manifest_sha256, "parent_manifest_sha256")

        annotations = tuple(_normalized_unique_strings(self.source_annotation_ids))
        object.__setattr__(self, "source_annotation_ids", annotations)

        raster_rows: list[tuple[str, str]] = []
        seen_raster_names: set[str] = set()
        for name, digest in self.raster_sha256_by_name:
            if not isinstance(name, str) or not name.strip():
                raise LabelsetVersionError("Raster hash names must not be blank.")
            normalized_name = name.strip()
            if normalized_name in seen_raster_names:
                raise LabelsetVersionError(
                    f"Duplicate raster hash name: {normalized_name}"
                )
            _require_sha256(digest, f"raster_sha256_by_name[{normalized_name}]")
            raster_rows.append((normalized_name, digest))
            seen_raster_names.add(normalized_name)
        object.__setattr__(self, "raster_sha256_by_name", tuple(sorted(raster_rows)))
        object.__setattr__(
            self,
            "created_at_utc",
            _as_utc(self.created_at_utc, "created_at_utc"),
        )

    def to_dict(self, *, include_manifest_hash: bool = True) -> dict[str, Any]:
        """Serialize the manifest using stable scalar fields."""

        payload: dict[str, Any] = {
            "labelset_name": self.labelset_name,
            "version": str(self.version),
            "labelset_id": self.labelset_id,
            "change_kind": self.change_kind.value,
            "parent_labelset_id": self.parent_labelset_id,
            "parent_manifest_sha256": self.parent_manifest_sha256,
            "label_content_sha256": self.label_content_sha256,
            "metadata_sha256": self.metadata_sha256,
            "semantics_sha256": self.semantics_sha256,
            "source_annotation_ids": list(self.source_annotation_ids),
            "raster_sha256_by_name": dict(self.raster_sha256_by_name),
            "created_at_utc": _iso_utc(self.created_at_utc),
        }
        if include_manifest_hash:
            payload["manifest_sha256"] = self.manifest_sha256
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> LabelsetManifest:
        """Load and validate a serialized manifest."""

        try:
            rasters = payload.get("raster_sha256_by_name", {})
            if not isinstance(rasters, Mapping):
                raise LabelsetVersionError(
                    "raster_sha256_by_name must be a JSON object."
                )
            return cls(
                labelset_name=payload["labelset_name"],
                version=SemanticVersion.parse(payload["version"]),
                labelset_id=payload["labelset_id"],
                change_kind=_coerce_change_kind(payload["change_kind"]),
                parent_labelset_id=payload.get("parent_labelset_id"),
                parent_manifest_sha256=payload.get("parent_manifest_sha256"),
                label_content_sha256=payload["label_content_sha256"],
                metadata_sha256=payload["metadata_sha256"],
                semantics_sha256=payload["semantics_sha256"],
                source_annotation_ids=tuple(payload.get("source_annotation_ids", ())),
                raster_sha256_by_name=tuple(
                    (str(name), str(digest)) for name, digest in rasters.items()
                ),
                created_at_utc=_parse_timestamp(payload["created_at_utc"]),
                manifest_sha256=payload["manifest_sha256"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, LabelsetVersionError):
                raise
            raise LabelsetVersionError(f"Invalid labelset manifest: {exc}") from exc


def build_labelset_manifest(
    *,
    labelset_name: str,
    version: SemanticVersion | str,
    change_kind: ChangeKind | str,
    label_content: Any,
    metadata: Any,
    semantics: Any,
    source_annotation_ids: tuple[str, ...] | list[str],
    raster_sha256_by_name: Mapping[str, str] | None = None,
    created_at_utc: datetime | None = None,
    parent: LabelsetManifest | None = None,
) -> LabelsetManifest:
    """Build a content-addressed manifest and enforce semantic bump rules."""

    parsed_version = SemanticVersion.parse(version)
    parsed_change = _coerce_change_kind(change_kind)
    source_ids = tuple(_normalized_unique_strings(source_annotation_ids))
    raster_hashes: dict[str, str] = {}
    for name, digest in (raster_sha256_by_name or {}).items():
        if not isinstance(name, str) or not name.strip():
            raise LabelsetVersionError("Raster hash names must not be blank.")
        normalized_name = name.strip()
        if normalized_name in raster_hashes:
            raise LabelsetVersionError(
                f"Duplicate normalized raster hash name: {normalized_name}"
            )
        _require_sha256(digest, f"raster_sha256_by_name[{normalized_name}]")
        raster_hashes[normalized_name] = digest

    label_content_sha256 = canonical_content_sha256(
        {
            "label_content": label_content,
            "source_annotation_ids": source_ids,
            "raster_sha256_by_name": raster_hashes,
        }
    )
    metadata_sha256 = canonical_content_sha256(metadata)
    semantics_sha256 = canonical_content_sha256(semantics)

    if parent is None:
        if parsed_change is not ChangeKind.INITIAL:
            raise LabelsetVersionError(
                "A labelset without a parent must declare change_kind='initial'."
            )
        parent_id = None
        parent_hash = None
    else:
        verify_manifest_integrity(parent)
        if parsed_change is ChangeKind.INITIAL:
            raise LabelsetVersionError(
                "A child labelset cannot declare change_kind='initial'."
            )
        expected_version = parent.version.next_for(parsed_change)
        if parsed_version != expected_version:
            raise LabelsetVersionError(
                f"{parsed_change.value} release must be {expected_version}; "
                f"received {parsed_version}."
            )
        if parent.labelset_name != labelset_name:
            raise LabelsetVersionError(
                "Parent and child labelset_name values must match."
            )
        _validate_change_hashes(
            parsed_change,
            parent=parent,
            label_content_sha256=label_content_sha256,
            metadata_sha256=metadata_sha256,
            semantics_sha256=semantics_sha256,
        )
        parent_id = parent.labelset_id
        parent_hash = parent.manifest_sha256

    created = _as_utc(
        created_at_utc or datetime.now(timezone.utc),
        "created_at_utc",
    )
    labelset_id = f"{labelset_name}_v{parsed_version}"
    unsigned = {
        "labelset_name": labelset_name,
        "version": str(parsed_version),
        "labelset_id": labelset_id,
        "change_kind": parsed_change.value,
        "parent_labelset_id": parent_id,
        "parent_manifest_sha256": parent_hash,
        "label_content_sha256": label_content_sha256,
        "metadata_sha256": metadata_sha256,
        "semantics_sha256": semantics_sha256,
        "source_annotation_ids": list(source_ids),
        "raster_sha256_by_name": dict(sorted(raster_hashes.items())),
        "created_at_utc": _iso_utc(created),
    }
    return LabelsetManifest(
        labelset_name=labelset_name,
        version=parsed_version,
        labelset_id=labelset_id,
        change_kind=parsed_change,
        parent_labelset_id=parent_id,
        parent_manifest_sha256=parent_hash,
        label_content_sha256=label_content_sha256,
        metadata_sha256=metadata_sha256,
        semantics_sha256=semantics_sha256,
        source_annotation_ids=source_ids,
        raster_sha256_by_name=tuple(sorted(raster_hashes.items())),
        created_at_utc=created,
        manifest_sha256=canonical_content_sha256(unsigned),
    )


def freeze_labelset_manifest(
    manifest: LabelsetManifest,
    path: str | Path,
) -> Path:
    """Write a verified manifest exactly once and refuse overwrite."""

    verify_manifest_integrity(manifest)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(
            manifest.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    try:
        descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise LabelsetVersionError(
            f"Frozen labelset manifest already exists and cannot be overwritten: {target}"
        ) from exc
    try:
        _write_all(descriptor, encoded)
        os.fsync(descriptor)
    except Exception:
        os.close(descriptor)
        target.unlink(missing_ok=True)
        raise
    else:
        os.close(descriptor)
    return target


def load_labelset_manifest(path: str | Path) -> LabelsetManifest:
    """Load a manifest and verify its self-contained content hash."""

    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LabelsetVersionError(f"Could not load labelset manifest {source}.") from exc
    if not isinstance(payload, Mapping):
        raise LabelsetVersionError("Labelset manifest root must be a JSON object.")
    manifest = LabelsetManifest.from_dict(payload)
    verify_manifest_integrity(manifest)
    return manifest


def verify_manifest_integrity(manifest: LabelsetManifest) -> None:
    """Raise when any self-contained manifest field has been mutated."""

    expected = canonical_content_sha256(manifest.to_dict(include_manifest_hash=False))
    if manifest.manifest_sha256 != expected:
        raise LabelsetVersionError(
            "Labelset manifest SHA-256 does not match its canonical content."
        )


def verify_labelset_content(
    manifest: LabelsetManifest,
    *,
    label_content: Any,
    metadata: Any,
    semantics: Any,
) -> None:
    """Verify external label, metadata, and semantic content against a manifest."""

    verify_manifest_integrity(manifest)
    observed_label_hash = canonical_content_sha256(
        {
            "label_content": label_content,
            "source_annotation_ids": manifest.source_annotation_ids,
            "raster_sha256_by_name": dict(manifest.raster_sha256_by_name),
        }
    )
    comparisons = {
        "label content": (observed_label_hash, manifest.label_content_sha256),
        "metadata": (canonical_content_sha256(metadata), manifest.metadata_sha256),
        "semantics": (canonical_content_sha256(semantics), manifest.semantics_sha256),
    }
    mismatches = [
        name for name, (observed, expected) in comparisons.items() if observed != expected
    ]
    if mismatches:
        raise LabelsetVersionError(
            "Frozen labelset content mismatch: " + ", ".join(mismatches) + "."
        )


def verify_manifest_lineage(
    child: LabelsetManifest,
    parent: LabelsetManifest,
) -> None:
    """Verify a child's parent pointer, hash, version bump, and change meaning."""

    verify_manifest_integrity(parent)
    verify_manifest_integrity(child)
    if child.parent_labelset_id != parent.labelset_id:
        raise LabelsetVersionError("Child parent_labelset_id does not match parent.")
    if child.parent_manifest_sha256 != parent.manifest_sha256:
        raise LabelsetVersionError("Child parent hash does not match parent manifest.")
    expected_version = parent.version.next_for(child.change_kind)
    if child.version != expected_version:
        raise LabelsetVersionError(
            f"Child version must be {expected_version} for a {child.change_kind.value} bump."
        )
    _validate_change_hashes(
        child.change_kind,
        parent=parent,
        label_content_sha256=child.label_content_sha256,
        metadata_sha256=child.metadata_sha256,
        semantics_sha256=child.semantics_sha256,
    )


def canonical_content_sha256(value: Any) -> str:
    """Return SHA-256 over canonical JSON, bytes, or a file's bytes."""

    if isinstance(value, Path):
        return file_sha256(value)
    if isinstance(value, bytes):
        return hashlib.sha256(value).hexdigest()
    canonical = _canonicalize(value)
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_sha256(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Hash a file without loading large rasters entirely into memory."""

    source = Path(path)
    if chunk_size <= 0:
        raise LabelsetVersionError("chunk_size must be greater than zero.")
    digest = hashlib.sha256()
    try:
        with source.open("rb") as handle:
            while chunk := handle.read(chunk_size):
                digest.update(chunk)
    except OSError as exc:
        raise LabelsetVersionError(f"Could not hash file {source}.") from exc
    return digest.hexdigest()


def _validate_change_hashes(
    change: ChangeKind,
    *,
    parent: LabelsetManifest,
    label_content_sha256: str,
    metadata_sha256: str,
    semantics_sha256: str,
) -> None:
    label_changed = label_content_sha256 != parent.label_content_sha256
    metadata_changed = metadata_sha256 != parent.metadata_sha256
    semantics_changed = semantics_sha256 != parent.semantics_sha256
    if change is ChangeKind.MAJOR:
        if not semantics_changed:
            raise LabelsetVersionError(
                "A major labelset release requires changed taxonomy, temporal, grid, or core semantics."
            )
        return
    if change is ChangeKind.MINOR:
        if semantics_changed:
            raise LabelsetVersionError(
                "Changed review semantics require a major labelset release."
            )
        if not label_changed:
            raise LabelsetVersionError(
                "A minor labelset release requires new or altered label content."
            )
        return
    if change is ChangeKind.PATCH:
        if semantics_changed or label_changed:
            raise LabelsetVersionError(
                "A patch release cannot change label pixels, source annotations, rasters, or semantics."
            )
        if not metadata_changed:
            raise LabelsetVersionError(
                "A patch release requires a metadata or QA correction."
            )
        return
    raise LabelsetVersionError("Child lineage cannot use change_kind='initial'.")


def _canonicalize(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _canonicalize(asdict(value))
    if isinstance(value, Enum):
        return _canonicalize(value.value)
    if isinstance(value, datetime):
        return _iso_utc(_as_utc(value, "datetime content"))
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, (str, int, float, bool)):
                raise LabelsetVersionError(
                    f"Canonical mapping key is not scalar: {key!r}."
                )
            normalized_key = str(key)
            if normalized_key in normalized:
                raise LabelsetVersionError(
                    f"Canonical mapping keys collide after normalization: {key!r}."
                )
            normalized[normalized_key] = _canonicalize(item)
        return normalized
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    if isinstance(value, (set, frozenset)):
        items = [_canonicalize(item) for item in value]
        return sorted(
            items,
            key=lambda item: json.dumps(
                item,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
    if isinstance(value, float) and not math.isfinite(value):
        raise LabelsetVersionError("Canonical content cannot contain NaN or infinity.")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise LabelsetVersionError(
        f"Unsupported canonical-content type: {type(value).__name__}."
    )


def _coerce_change_kind(value: ChangeKind | str) -> ChangeKind:
    if isinstance(value, ChangeKind):
        return value
    try:
        return ChangeKind(value)
    except (TypeError, ValueError) as exc:
        raise LabelsetVersionError(f"Unknown labelset change kind: {value!r}.") from exc


def _normalized_unique_strings(values: Any) -> list[str]:
    if isinstance(values, (str, bytes)):
        raise LabelsetVersionError("Expected a sequence of annotation IDs.")
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise LabelsetVersionError("Annotation IDs must be non-blank strings.")
        text = value.strip()
        if text in normalized:
            raise LabelsetVersionError(f"Duplicate source annotation ID: {text}")
        normalized.append(text)
    return normalized


def _require_sha256(value: Any, field_name: str) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise LabelsetVersionError(
            f"{field_name} must be a lowercase 64-character SHA-256 digest."
        )


def _as_utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise LabelsetVersionError(f"{field_name} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise LabelsetVersionError(f"{field_name} must be timezone-aware.")
    return value.astimezone(timezone.utc)


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise LabelsetVersionError("created_at_utc must not be blank.")
    try:
        return _as_utc(
            datetime.fromisoformat(value.strip().replace("Z", "+00:00")),
            "created_at_utc",
        )
    except ValueError as exc:
        raise LabelsetVersionError(f"Invalid created_at_utc: {value!r}.") from exc


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_all(descriptor: int, data: bytes) -> None:
    view = memoryview(data)
    written = 0
    while written < len(view):
        count = os.write(descriptor, view[written:])
        if count <= 0:
            raise OSError("Could not write complete manifest.")
        written += count
