"""Fail-closed event and source-asset registry for the flood-label factory.

The registry is deliberately metadata-only.  It validates temporal, grid,
rights, checksum, and provenance contracts without opening imagery or treating
the current Mae Sai weak mask as human-reviewed evidence.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from numbers import Integral, Real
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
from typing import TypeAlias

import pandas as pd

from floodguard.label_factory.contracts import DatasetRole
from floodguard.label_factory.tiling import (
    GridContractError,
    ProjectedGridSpec,
    validate_event_id,
    validate_projected_metre_crs,
)


class EventRegistryError(ValueError):
    """Raised when event/source metadata are incomplete or unsafe to use."""


EVENT_REQUIRED_COLUMNS: tuple[str, ...] = (
    "event_id",
    "event_name",
    "country",
    "study_area",
    "event_start_utc",
    "event_end_utc",
    "pre_acquisition_utc",
    "post_acquisition_utc",
    "analysis_crs",
    "analysis_resolution_m",
    "grid_origin_x",
    "grid_origin_y",
    "tile_size_pixels",
    "query_size_pixels",
    "dataset_role",
    "label_status",
    "source_rights_status",
    "processing_allowed",
    "ml_label_derivation_allowed",
    "validation_allowed",
    "source_timestamp",
    "confidence_class",
    "assumptions",
)

SOURCE_ASSET_REQUIRED_COLUMNS: tuple[str, ...] = (
    "asset_id",
    "event_id",
    "sensor",
    "platform",
    "product_id",
    "acquisition_time_utc",
    "event_relative_role",
    "orbit_direction",
    "relative_orbit",
    "polarizations",
    "processing_level",
    "crs",
    "pixel_spacing_m",
    "local_path_hint",
    "sha256",
    "sha256_status",
    "license_status",
    "processing_allowed",
    "ml_label_derivation_allowed",
    "redistribution_status",
    "georegistration_method",
    "georegistration_error_pixels",
    "source_timestamp",
    "confidence_class",
    "assumptions",
)

CONFIDENCE_CLASSES = frozenset({"high", "medium", "low"})
SOURCE_EVENT_ROLES = frozenset(
    {"pre_event", "event_time", "post_event", "static_context"}
)
CHECKSUM_STATUSES = frozenset({"recorded", "verified"})
# Canonical review imagery is blocked above this residual alignment error.
MAX_GEOREGISTRATION_ERROR_PIXELS = 0.5
_RIGHTS_BLOCKING_STATUSES = frozenset(
    {
        "blocked",
        "denied",
        "expired",
        "not_allowed",
        "not_cleared",
        "prohibited",
        "unknown",
        "unresolved",
    }
)
_ASSET_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*")
_SHA256_PATTERN = re.compile(r"[0-9a-fA-F]{64}")

TabularInput: TypeAlias = (
    pd.DataFrame
    | str
    | Path
    | Mapping[str, object]
    | Iterable[Mapping[str, object]]
)


@dataclass(frozen=True)
class EventRecord:
    """One immutable event, temporal target, grid, role, and rights contract."""

    event_id: str
    event_name: str
    country: str
    study_area: str
    event_start_utc: datetime
    event_end_utc: datetime
    pre_acquisition_utc: datetime
    post_acquisition_utc: datetime
    analysis_crs: str
    analysis_resolution_m: float
    grid_origin_x: float
    grid_origin_y: float
    tile_size_pixels: int
    query_size_pixels: int
    dataset_role: DatasetRole
    label_status: str
    source_rights_status: str
    processing_allowed: bool
    ml_label_derivation_allowed: bool
    validation_allowed: bool
    source_timestamp: datetime
    confidence_class: str
    assumptions: str

    @classmethod
    def from_mapping(cls, row: Mapping[str, object]) -> EventRecord:
        """Build and validate one event from a CSV-like mapping."""

        _require_columns(row, EVENT_REQUIRED_COLUMNS, "event")
        event_id = _text(row, "event_id")
        try:
            validate_event_id(event_id)
        except GridContractError as exc:
            raise EventRegistryError(str(exc)) from exc

        start = parse_utc_datetime(row["event_start_utc"], "event_start_utc")
        end = parse_utc_datetime(row["event_end_utc"], "event_end_utc")
        pre = parse_utc_datetime(row["pre_acquisition_utc"], "pre_acquisition_utc")
        post = parse_utc_datetime(
            row["post_acquisition_utc"], "post_acquisition_utc"
        )
        source_timestamp = parse_utc_datetime(
            row["source_timestamp"], "source_timestamp"
        )
        if start > end:
            raise EventRegistryError("event_start_utc must not follow event_end_utc.")
        if pre >= post:
            raise EventRegistryError(
                "pre_acquisition_utc must be strictly before post_acquisition_utc."
            )
        if pre >= start:
            raise EventRegistryError(
                "pre_acquisition_utc must be strictly before event_start_utc."
            )
        if post < start:
            raise EventRegistryError(
                "post_acquisition_utc must be at or after event_start_utc."
            )
        if source_timestamp < max(pre, post):
            raise EventRegistryError(
                "source_timestamp cannot predate the declared acquisitions."
            )

        analysis_crs = _projected_crs(row["analysis_crs"], "analysis_crs")
        resolution = _positive_float(
            row["analysis_resolution_m"], "analysis_resolution_m"
        )
        origin_x = _finite_float(row["grid_origin_x"], "grid_origin_x")
        origin_y = _finite_float(row["grid_origin_y"], "grid_origin_y")
        tile_size = _positive_int(row["tile_size_pixels"], "tile_size_pixels")
        query_size = _positive_int(row["query_size_pixels"], "query_size_pixels")
        if tile_size % query_size:
            raise EventRegistryError(
                "query_size_pixels must divide tile_size_pixels exactly."
            )
        # Constructing the shared type also freezes its normalization rules.
        try:
            ProjectedGridSpec(
                crs=analysis_crs,
                resolution_m=resolution,
                tile_size_cells=tile_size,
                origin_x=origin_x,
                origin_y=origin_y,
            )
        except GridContractError as exc:
            raise EventRegistryError(str(exc)) from exc

        dataset_role = _dataset_role(row["dataset_role"])
        processing_allowed = strict_bool(
            row["processing_allowed"], "processing_allowed"
        )
        derivation_allowed = strict_bool(
            row["ml_label_derivation_allowed"],
            "ml_label_derivation_allowed",
        )
        validation_allowed = strict_bool(
            row["validation_allowed"], "validation_allowed"
        )
        rights_status = _text(row, "source_rights_status")
        _validate_rights_consistency(
            rights_status,
            any_allowed=(
                processing_allowed or derivation_allowed or validation_allowed
            ),
            field_name="source_rights_status",
        )
        if derivation_allowed and not processing_allowed:
            raise EventRegistryError(
                "ml_label_derivation_allowed requires processing_allowed=true."
            )
        if validation_allowed and not processing_allowed:
            raise EventRegistryError(
                "validation_allowed requires processing_allowed=true."
            )

        return cls(
            event_id=event_id,
            event_name=_text(row, "event_name"),
            country=_text(row, "country"),
            study_area=_text(row, "study_area"),
            event_start_utc=start,
            event_end_utc=end,
            pre_acquisition_utc=pre,
            post_acquisition_utc=post,
            analysis_crs=analysis_crs,
            analysis_resolution_m=resolution,
            grid_origin_x=origin_x,
            grid_origin_y=origin_y,
            tile_size_pixels=tile_size,
            query_size_pixels=query_size,
            dataset_role=dataset_role,
            label_status=_text(row, "label_status"),
            source_rights_status=rights_status,
            processing_allowed=processing_allowed,
            ml_label_derivation_allowed=derivation_allowed,
            validation_allowed=validation_allowed,
            source_timestamp=source_timestamp,
            confidence_class=_confidence(row["confidence_class"]),
            assumptions=_text(row, "assumptions"),
        )

    @property
    def grid(self) -> ProjectedGridSpec:
        """Return the canonical projected-grid contract for this event."""

        return ProjectedGridSpec(
            crs=self.analysis_crs,
            resolution_m=self.analysis_resolution_m,
            tile_size_cells=self.tile_size_pixels,
            origin_x=self.grid_origin_x,
            origin_y=self.grid_origin_y,
        )

    def as_manifest_row(self) -> dict[str, object]:
        """Return canonical scalar values suitable for a CSV manifest."""

        return {
            "event_id": self.event_id,
            "event_name": self.event_name,
            "country": self.country,
            "study_area": self.study_area,
            "event_start_utc": format_utc_datetime(self.event_start_utc),
            "event_end_utc": format_utc_datetime(self.event_end_utc),
            "pre_acquisition_utc": format_utc_datetime(self.pre_acquisition_utc),
            "post_acquisition_utc": format_utc_datetime(self.post_acquisition_utc),
            "analysis_crs": self.analysis_crs,
            "analysis_resolution_m": self.analysis_resolution_m,
            "grid_origin_x": self.grid_origin_x,
            "grid_origin_y": self.grid_origin_y,
            "tile_size_pixels": self.tile_size_pixels,
            "query_size_pixels": self.query_size_pixels,
            "dataset_role": self.dataset_role.value,
            "label_status": self.label_status,
            "source_rights_status": self.source_rights_status,
            "processing_allowed": self.processing_allowed,
            "ml_label_derivation_allowed": self.ml_label_derivation_allowed,
            "validation_allowed": self.validation_allowed,
            "source_timestamp": format_utc_datetime(self.source_timestamp),
            "confidence_class": self.confidence_class,
            "assumptions": self.assumptions,
        }


@dataclass(frozen=True)
class SourceAssetRecord:
    """One checksum-backed, rights-qualified, georegistered source asset."""

    asset_id: str
    event_id: str
    sensor: str
    platform: str
    product_id: str
    acquisition_time_utc: datetime
    event_relative_role: str
    orbit_direction: str
    relative_orbit: str
    polarizations: str
    processing_level: str
    crs: str
    pixel_spacing_m: float
    local_path_hint: str
    sha256: str
    sha256_status: str
    license_status: str
    processing_allowed: bool
    ml_label_derivation_allowed: bool
    redistribution_status: str
    georegistration_method: str
    georegistration_error_pixels: float
    source_timestamp: datetime
    confidence_class: str
    assumptions: str

    @classmethod
    def from_mapping(cls, row: Mapping[str, object]) -> SourceAssetRecord:
        """Build and validate one source asset from a CSV-like mapping."""

        _require_columns(row, SOURCE_ASSET_REQUIRED_COLUMNS, "source asset")
        asset_id = _text(row, "asset_id")
        if _ASSET_ID_PATTERN.fullmatch(asset_id) is None:
            raise EventRegistryError(
                "asset_id must use letters, digits, dot, underscore, colon, or hyphen."
            )
        event_id = _text(row, "event_id")
        try:
            validate_event_id(event_id)
        except GridContractError as exc:
            raise EventRegistryError(str(exc)) from exc
        acquisition = parse_utc_datetime(
            row["acquisition_time_utc"], "acquisition_time_utc"
        )
        source_timestamp = parse_utc_datetime(
            row["source_timestamp"], "source_timestamp"
        )
        if source_timestamp < acquisition:
            raise EventRegistryError(
                "source_timestamp cannot predate acquisition_time_utc."
            )
        event_relative_role = _text(row, "event_relative_role")
        if event_relative_role not in SOURCE_EVENT_ROLES:
            raise EventRegistryError(
                "event_relative_role must be one of: "
                + ", ".join(sorted(SOURCE_EVENT_ROLES))
                + "."
            )
        crs = _projected_crs(row["crs"], "crs")
        path_hint = _text(row, "local_path_hint")
        reject_absolute_local_path(path_hint)
        sha256 = _text(row, "sha256").lower()
        if _SHA256_PATTERN.fullmatch(sha256) is None:
            raise EventRegistryError("sha256 must contain exactly 64 hexadecimal digits.")
        sha256_status = _text(row, "sha256_status").lower()
        if sha256_status not in CHECKSUM_STATUSES:
            raise EventRegistryError(
                "sha256_status must be 'recorded' or 'verified' when a source "
                "enters the label-factory registry."
            )
        processing_allowed = strict_bool(
            row["processing_allowed"], "processing_allowed"
        )
        derivation_allowed = strict_bool(
            row["ml_label_derivation_allowed"],
            "ml_label_derivation_allowed",
        )
        license_status = _text(row, "license_status")
        _validate_rights_consistency(
            license_status,
            any_allowed=processing_allowed or derivation_allowed,
            field_name="license_status",
        )
        if derivation_allowed and not processing_allowed:
            raise EventRegistryError(
                "Source ml_label_derivation_allowed requires processing_allowed=true."
            )

        return cls(
            asset_id=asset_id,
            event_id=event_id,
            sensor=_text(row, "sensor"),
            platform=_text(row, "platform"),
            product_id=_text(row, "product_id"),
            acquisition_time_utc=acquisition,
            event_relative_role=event_relative_role,
            orbit_direction=_text(row, "orbit_direction"),
            relative_orbit=_text(row, "relative_orbit"),
            polarizations=_text(row, "polarizations"),
            processing_level=_text(row, "processing_level"),
            crs=crs,
            pixel_spacing_m=_positive_float(
                row["pixel_spacing_m"], "pixel_spacing_m"
            ),
            local_path_hint=path_hint,
            sha256=sha256,
            sha256_status=sha256_status,
            license_status=license_status,
            processing_allowed=processing_allowed,
            ml_label_derivation_allowed=derivation_allowed,
            redistribution_status=_text(row, "redistribution_status"),
            georegistration_method=_text(row, "georegistration_method"),
            georegistration_error_pixels=_nonnegative_float(
                row["georegistration_error_pixels"],
                "georegistration_error_pixels",
            ),
            source_timestamp=source_timestamp,
            confidence_class=_confidence(row["confidence_class"]),
            assumptions=_text(row, "assumptions"),
        )

    def as_manifest_row(self) -> dict[str, object]:
        """Return canonical scalar values suitable for a CSV manifest."""

        return {
            "asset_id": self.asset_id,
            "event_id": self.event_id,
            "sensor": self.sensor,
            "platform": self.platform,
            "product_id": self.product_id,
            "acquisition_time_utc": format_utc_datetime(
                self.acquisition_time_utc
            ),
            "event_relative_role": self.event_relative_role,
            "orbit_direction": self.orbit_direction,
            "relative_orbit": self.relative_orbit,
            "polarizations": self.polarizations,
            "processing_level": self.processing_level,
            "crs": self.crs,
            "pixel_spacing_m": self.pixel_spacing_m,
            "local_path_hint": self.local_path_hint,
            "sha256": self.sha256,
            "sha256_status": self.sha256_status,
            "license_status": self.license_status,
            "processing_allowed": self.processing_allowed,
            "ml_label_derivation_allowed": self.ml_label_derivation_allowed,
            "redistribution_status": self.redistribution_status,
            "georegistration_method": self.georegistration_method,
            "georegistration_error_pixels": self.georegistration_error_pixels,
            "source_timestamp": format_utc_datetime(self.source_timestamp),
            "confidence_class": self.confidence_class,
            "assumptions": self.assumptions,
        }


def load_events(source: TabularInput) -> tuple[EventRecord, ...]:
    """Load events from mappings, a DataFrame, or a CSV and reject duplicates."""

    frame = _load_frame(source, "events")
    _require_frame_columns(frame, EVENT_REQUIRED_COLUMNS, "events")
    records = tuple(EventRecord.from_mapping(row) for row in frame.to_dict("records"))
    _require_nonempty(records, "events")
    _reject_duplicate_values((record.event_id for record in records), "event_id")
    return records


def load_source_assets(source: TabularInput) -> tuple[SourceAssetRecord, ...]:
    """Load source assets from mappings, a DataFrame, or a CSV."""

    frame = _load_frame(source, "source assets")
    _require_frame_columns(frame, SOURCE_ASSET_REQUIRED_COLUMNS, "source assets")
    records = tuple(
        SourceAssetRecord.from_mapping(row) for row in frame.to_dict("records")
    )
    _require_nonempty(records, "source assets")
    _reject_duplicate_values((record.asset_id for record in records), "asset_id")
    return records


def validate_event_source_registry(
    events: Sequence[EventRecord],
    source_assets: Sequence[SourceAssetRecord],
    *,
    require_label_factory_rights: bool = True,
    require_complete_acquisition_pair: bool = True,
    require_canonical_alignment: bool = True,
) -> None:
    """Cross-check sources against immutable event, rights, and grid contracts.

    The strict defaults are intended for actual label-factory use.  Callers may
    load individual records for planning, but a build is blocked until each
    event has rights-cleared, checksum-backed pre and event/post acquisitions
    aligned to the canonical projected grid with residual registration error
    no greater than ``MAX_GEOREGISTRATION_ERROR_PIXELS``.
    """

    _require_nonempty(events, "events")
    _require_nonempty(source_assets, "source assets")
    _reject_duplicate_values((record.event_id for record in events), "event_id")
    _reject_duplicate_values((record.asset_id for record in source_assets), "asset_id")
    event_by_id = {event.event_id: event for event in events}
    assets_by_event: dict[str, list[SourceAssetRecord]] = {
        event_id: [] for event_id in event_by_id
    }
    for asset in source_assets:
        event = event_by_id.get(asset.event_id)
        if event is None:
            raise EventRegistryError(
                f"Source asset {asset.asset_id!r} references unknown event "
                f"{asset.event_id!r}."
            )
        assets_by_event[event.event_id].append(asset)
        _validate_asset_temporal_role(asset, event)
        if require_canonical_alignment:
            if asset.crs != event.analysis_crs:
                raise EventRegistryError(
                    f"Source asset {asset.asset_id!r} CRS {asset.crs} does not "
                    f"match event grid {event.analysis_crs}."
                )
            if not _numbers_equal(
                asset.pixel_spacing_m, event.analysis_resolution_m
            ):
                raise EventRegistryError(
                    f"Source asset {asset.asset_id!r} pixel spacing does not "
                    "match analysis_resolution_m."
                )
            if (
                asset.georegistration_error_pixels
                > MAX_GEOREGISTRATION_ERROR_PIXELS
            ):
                raise EventRegistryError(
                    f"Source asset {asset.asset_id!r} georegistration error "
                    f"{asset.georegistration_error_pixels:g} pixels exceeds the "
                    f"canonical maximum of {MAX_GEOREGISTRATION_ERROR_PIXELS:g} "
                    "pixels."
                )
        if require_label_factory_rights and (
            not asset.processing_allowed or not asset.ml_label_derivation_allowed
        ):
            raise EventRegistryError(
                f"Source asset {asset.asset_id!r} is not rights-cleared for "
                "processing and label derivation."
            )

    for event in events:
        if require_label_factory_rights and (
            not event.processing_allowed or not event.ml_label_derivation_allowed
        ):
            raise EventRegistryError(
                f"Event {event.event_id!r} is not rights-cleared for processing "
                "and label derivation."
            )
        if (
            event.dataset_role
            in {
                DatasetRole.FIXED_WITHIN_EVENT_DEVELOPMENT,
                DatasetRole.UNTOUCHED_GEOGRAPHIC_TEST,
            }
            and not event.validation_allowed
        ):
            raise EventRegistryError(
                f"Event {event.event_id!r} has a validation/test role but "
                "validation_allowed=false."
            )
        event_assets = assets_by_event[event.event_id]
        if not event_assets:
            raise EventRegistryError(
                f"Event {event.event_id!r} has no registered source assets."
            )
        if require_complete_acquisition_pair:
            acquisition_times = {
                asset.acquisition_time_utc
                for asset in event_assets
                if asset.event_relative_role != "static_context"
            }
            if event.pre_acquisition_utc not in acquisition_times:
                raise EventRegistryError(
                    f"Event {event.event_id!r} has no source asset for its "
                    "pre_acquisition_utc."
                )
            if event.post_acquisition_utc not in acquisition_times:
                raise EventRegistryError(
                    f"Event {event.event_id!r} has no source asset for its "
                    "post_acquisition_utc."
                )
        if require_canonical_alignment:
            _validate_sar_acquisition_pair_compatibility(event, event_assets)


def parse_utc_datetime(value: object, field_name: str) -> datetime:
    """Parse an explicitly UTC timestamp and normalize it to ``datetime``."""

    if _is_missing(value):
        raise EventRegistryError(f"{field_name} must be a non-blank UTC timestamp.")
    if isinstance(value, pd.Timestamp):
        parsed = value.to_pydatetime()
    elif isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if not (text.endswith("Z") or text.endswith("+00:00")):
            raise EventRegistryError(
                f"{field_name} must include an explicit UTC offset (Z or +00:00)."
            )
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise EventRegistryError(
                f"{field_name} is not a valid ISO-8601 UTC timestamp."
            ) from exc
    else:
        raise EventRegistryError(
            f"{field_name} must be an ISO-8601 UTC timestamp."
        )
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise EventRegistryError(f"{field_name} must use UTC, not a local offset.")
    return parsed.astimezone(UTC)


def format_utc_datetime(value: datetime) -> str:
    """Format a validated timestamp in canonical ``Z`` notation."""

    parsed = parse_utc_datetime(value, "timestamp")
    return parsed.isoformat().replace("+00:00", "Z")


def strict_bool(value: object, field_name: str) -> bool:
    """Parse booleans without accepting ambiguous numeric truthiness."""

    if isinstance(value, bool):
        return value
    # pandas may surface numpy.bool_ without making numpy a direct dependency.
    if type(value).__name__ == "bool_":
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    raise EventRegistryError(f"{field_name} must be exactly true or false.")


def reject_absolute_local_path(path_hint: str) -> None:
    """Reject absolute, home-relative, URI, and parent-traversal path hints."""

    if (
        PureWindowsPath(path_hint).is_absolute()
        or PurePosixPath(path_hint).is_absolute()
        or path_hint.startswith(("~", "\\\\"))
        or "://" in path_hint
        or ".." in PureWindowsPath(path_hint).parts
        or ".." in PurePosixPath(path_hint).parts
    ):
        raise EventRegistryError(
            "local_path_hint must be a redacted relative hint, never an absolute "
            "local path, URI, home shortcut, or parent traversal."
        )


def _load_frame(source: TabularInput, label: str) -> pd.DataFrame:
    if isinstance(source, pd.DataFrame):
        return source.copy()
    if isinstance(source, (str, Path)):
        path = Path(source)
        if path.suffix.lower() != ".csv":
            raise EventRegistryError(f"{label} input must be a CSV file.")
        if not path.is_file():
            raise EventRegistryError(f"{label} CSV does not exist: {path}")
        try:
            return pd.read_csv(path)
        except (OSError, pd.errors.ParserError, UnicodeError) as exc:
            raise EventRegistryError(f"Could not read {label} CSV: {exc}") from exc
    if isinstance(source, Mapping):
        return pd.DataFrame([dict(source)])
    try:
        return pd.DataFrame(list(source))
    except (TypeError, ValueError) as exc:
        raise EventRegistryError(f"Could not convert {label} input to rows.") from exc


def _require_frame_columns(
    frame: pd.DataFrame, required: Sequence[str], label: str
) -> None:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise EventRegistryError(
            f"{label} is missing required columns: {', '.join(missing)}."
        )


def _require_columns(
    row: Mapping[str, object], required: Sequence[str], label: str
) -> None:
    missing = [column for column in required if column not in row]
    if missing:
        raise EventRegistryError(
            f"{label} row is missing required fields: {', '.join(missing)}."
        )


def _text(row: Mapping[str, object], field_name: str) -> str:
    value = row[field_name]
    if _is_missing(value):
        raise EventRegistryError(f"{field_name} must not be blank.")
    text = str(value).strip()
    if not text:
        raise EventRegistryError(f"{field_name} must not be blank.")
    return text


def _dataset_role(value: object) -> DatasetRole:
    if _is_missing(value):
        raise EventRegistryError("dataset_role must not be blank.")
    try:
        return DatasetRole(str(value).strip())
    except ValueError as exc:
        raise EventRegistryError(
            "dataset_role must use one of: "
            + ", ".join(role.value for role in DatasetRole)
            + "."
        ) from exc


def _confidence(value: object) -> str:
    if _is_missing(value):
        raise EventRegistryError("confidence_class must not be blank.")
    normalized = str(value).strip().lower()
    if normalized not in CONFIDENCE_CLASSES:
        raise EventRegistryError("confidence_class must be high, medium, or low.")
    return normalized


def _projected_crs(value: object, field_name: str) -> str:
    if _is_missing(value):
        raise EventRegistryError(f"{field_name} must not be blank.")
    try:
        return validate_projected_metre_crs(str(value).strip())
    except GridContractError as exc:
        raise EventRegistryError(f"{field_name}: {exc}") from exc


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or _is_missing(value):
        raise EventRegistryError(f"{field_name} must be a positive integer.")
    if isinstance(value, Integral):
        parsed = int(value)
    elif isinstance(value, Real) and float(value).is_integer():
        parsed = int(value)
    elif isinstance(value, str):
        try:
            parsed = int(value.strip())
        except ValueError as exc:
            raise EventRegistryError(
                f"{field_name} must be a positive integer."
            ) from exc
    else:
        raise EventRegistryError(f"{field_name} must be a positive integer.")
    if parsed <= 0:
        raise EventRegistryError(f"{field_name} must be a positive integer.")
    return parsed


def _finite_float(value: object, field_name: str) -> float:
    if isinstance(value, bool) or _is_missing(value):
        raise EventRegistryError(f"{field_name} must be a finite number.")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise EventRegistryError(f"{field_name} must be a finite number.") from exc
    if not pd.notna(parsed) or parsed in {float("inf"), float("-inf")}:
        raise EventRegistryError(f"{field_name} must be a finite number.")
    return parsed


def _positive_float(value: object, field_name: str) -> float:
    parsed = _finite_float(value, field_name)
    if parsed <= 0:
        raise EventRegistryError(f"{field_name} must be positive.")
    return parsed


def _nonnegative_float(value: object, field_name: str) -> float:
    parsed = _finite_float(value, field_name)
    if parsed < 0:
        raise EventRegistryError(f"{field_name} must be non-negative.")
    return parsed


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    try:
        result = pd.isna(value)
        return bool(result) if isinstance(result, (bool,)) or type(result).__name__ == "bool_" else False
    except (TypeError, ValueError):
        return False


def _validate_rights_consistency(
    status: str, *, any_allowed: bool, field_name: str
) -> None:
    normalized = status.strip().lower().replace(" ", "_")
    if any_allowed and normalized in _RIGHTS_BLOCKING_STATUSES:
        raise EventRegistryError(
            f"{field_name}={status!r} contradicts an allowed-use flag."
        )


def _validate_asset_temporal_role(
    asset: SourceAssetRecord, event: EventRecord
) -> None:
    timestamp = asset.acquisition_time_utc
    role = asset.event_relative_role
    if role == "pre_event" and timestamp >= event.event_start_utc:
        raise EventRegistryError(
            f"Source asset {asset.asset_id!r} is marked pre_event but was not "
            "acquired before event_start_utc."
        )
    if role == "event_time" and not (
        event.event_start_utc <= timestamp <= event.event_end_utc
    ):
        raise EventRegistryError(
            f"Source asset {asset.asset_id!r} is marked event_time but falls "
            "outside the event window."
        )
    if role == "post_event" and timestamp <= event.event_end_utc:
        raise EventRegistryError(
            f"Source asset {asset.asset_id!r} is marked post_event but was not "
            "acquired after event_end_utc."
        )


def _validate_sar_acquisition_pair_compatibility(
    event: EventRecord, assets: Sequence[SourceAssetRecord]
) -> None:
    """Require comparable metadata for the event's declared SAR change pair.

    Static context and non-SAR assets are deliberately excluded.  When both
    sides of the declared acquisition pair contain SAR assets, all registered
    alternatives must agree on viewing direction, relative orbit, and the
    available polarization set.  Polarization ordering and case are not
    meaningful and are normalized before comparison.
    """

    pre_assets = [
        asset
        for asset in assets
        if asset.acquisition_time_utc == event.pre_acquisition_utc
        and asset.event_relative_role != "static_context"
        and _is_sar_asset(asset)
    ]
    post_assets = [
        asset
        for asset in assets
        if asset.acquisition_time_utc == event.post_acquisition_utc
        and asset.event_relative_role != "static_context"
        and _is_sar_asset(asset)
    ]
    if not pre_assets or not post_assets:
        return

    comparisons = (
        ("orbit_direction", lambda asset: asset.orbit_direction.casefold()),
        ("relative_orbit", lambda asset: _normalized_relative_orbit(asset)),
        ("polarizations", lambda asset: _normalized_polarizations(asset)),
    )
    for field_name, normalizer in comparisons:
        pre_values = {normalizer(asset) for asset in pre_assets}
        post_values = {normalizer(asset) for asset in post_assets}
        if pre_values != post_values:
            raise EventRegistryError(
                f"Event {event.event_id!r} declared pre/post SAR pair has "
                f"incompatible {field_name}: pre assets "
                f"{_asset_ids(pre_assets)} do not match post assets "
                f"{_asset_ids(post_assets)}."
            )


def _is_sar_asset(asset: SourceAssetRecord) -> bool:
    return (
        re.search(
            r"(?:^|[^A-Z0-9])SAR(?:$|[^A-Z0-9])", asset.sensor.upper()
        )
        is not None
    )


def _normalized_relative_orbit(asset: SourceAssetRecord) -> str:
    value = asset.relative_orbit.strip().casefold()
    if value.isdigit():
        return str(int(value))
    return value


def _normalized_polarizations(asset: SourceAssetRecord) -> frozenset[str]:
    return frozenset(
        token.upper()
        for token in re.split(r"[,;/\s]+", asset.polarizations.strip())
        if token
    )


def _asset_ids(assets: Sequence[SourceAssetRecord]) -> str:
    return "[" + ", ".join(repr(asset.asset_id) for asset in assets) + "]"


def _numbers_equal(left: float, right: float) -> bool:
    tolerance = max(abs(left), abs(right), 1.0) * 1e-12
    return abs(left - right) <= tolerance


def _require_nonempty(values: Sequence[object], label: str) -> None:
    if not values:
        raise EventRegistryError(f"{label} must contain at least one row.")


def _reject_duplicate_values(values: Iterable[str], field_name: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise EventRegistryError(f"Duplicate {field_name}: {value!r}.")
        seen.add(value)
