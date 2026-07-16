"""Typed, fail-closed run contract for candidate GeoAI work."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
PRIVATE_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/]|\\\\|/(?:Users|home|root|tmp|var|private)/)",
    re.IGNORECASE,
)


class ContractError(ValueError):
    """Raised when a run would violate a reproducibility or safety gate."""


@dataclass(frozen=True, slots=True)
class InputManifestRow:
    """One immutable model input and its upstream permission state."""

    role: str
    product_id: str
    sha256: str
    source_timestamp: str
    processing_allowed: bool

    def validate(self) -> None:
        if (
            not isinstance(self.role, str)
            or not self.role.strip()
            or not isinstance(self.product_id, str)
            or not self.product_id.strip()
        ):
            raise ContractError("Each input requires a role and product ID.")
        if not isinstance(self.sha256, str) or not SHA256_RE.fullmatch(self.sha256):
            raise ContractError(f"Input {self.product_id!r} requires a lowercase SHA-256.")
        if not isinstance(self.source_timestamp, str):
            raise ContractError("input source_timestamp must be a string.")
        _require_rfc3339(self.source_timestamp, "input source_timestamp")
        if type(self.processing_allowed) is not bool:
            raise ContractError("processing_allowed must be a strict boolean.")


@dataclass(frozen=True, slots=True)
class BandTransformContract:
    """One auditable physical-value transform bound to the sidecar receipt."""

    name: str
    physical_min: float
    physical_max: float
    units: str
    description: str

    def validate(self) -> None:
        text_values = (self.name, self.units, self.description)
        if any(not isinstance(value, str) or not value.strip() for value in text_values):
            raise ContractError("Band transform text fields must be non-empty strings.")
        limits = (self.physical_min, self.physical_max)
        if (
            any(
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or not math.isfinite(value)
                for value in limits
            )
            or self.physical_min >= self.physical_max
        ):
            raise ContractError(f"Band transform limits are invalid for {self.name!r}.")


@dataclass(frozen=True, slots=True)
class PreprocessingContract:
    """Frozen physical-value to uint8 transform used by train and inference."""

    method: Literal["clip_linear_uint8_v1"]
    channel_names: tuple[str, ...]
    transforms: tuple[BandTransformContract, ...]
    sidecar_sha256: str
    encoded_dtype: Literal["uint8"] = "uint8"
    encoded_range: tuple[int, int] = (0, 255)
    stock_geoai_divisor: int = 255

    def validate(self) -> None:
        if self.method != "clip_linear_uint8_v1" or self.encoded_dtype != "uint8":
            raise ContractError("Preprocessing method and encoded dtype are frozen.")
        if not isinstance(self.channel_names, tuple):
            raise ContractError("Preprocessing channel names must be an ordered tuple.")
        valid_names = all(
            isinstance(name, str) and bool(name.strip()) for name in self.channel_names
        )
        if not valid_names:
            raise ContractError("Preprocessing channel names must be non-empty strings.")
        valid_count = 6 <= len(self.channel_names) <= 8
        unique_names = len(set(self.channel_names)) == len(self.channel_names)
        if not valid_count or not unique_names:
            raise ContractError("GeoAI requires 6-8 unique, ordered channel names.")
        if (
            not isinstance(self.transforms, tuple)
            or len(self.transforms) != len(self.channel_names)
            or any(
                not isinstance(transform, BandTransformContract) for transform in self.transforms
            )
        ):
            raise ContractError("Typed per-band transform statistics are required.")
        for transform in self.transforms:
            transform.validate()
        if tuple(transform.name for transform in self.transforms) != self.channel_names:
            raise ContractError("Transform statistics must match the ordered channel names.")
        if not isinstance(self.sidecar_sha256, str) or not SHA256_RE.fullmatch(self.sidecar_sha256):
            raise ContractError("Preprocessing sidecar SHA-256 is required.")
        valid_range = (
            isinstance(self.encoded_range, tuple)
            and len(self.encoded_range) == 2
            and all(type(value) is int for value in self.encoded_range)
            and self.encoded_range == (0, 255)
        )
        if (
            not valid_range
            or type(self.stock_geoai_divisor) is not int
            or self.stock_geoai_divisor != 255
        ):
            raise ContractError("Stock GeoAI training requires the frozen uint8/255 contract.")


@dataclass(frozen=True, slots=True)
class ValidationMetricsContract:
    """Validation evidence bound to any decision-layer promotion claim."""

    iou: float | None
    f1_dice: float | None
    precision: float | None
    recall: float | None
    area_error_ratio: float | None
    brier_score: float | None
    expected_calibration_error: float | None

    @property
    def is_complete(self) -> bool:
        return all(value is not None for value in self.as_dict().values())

    def as_dict(self) -> dict[str, float | None]:
        return {
            "iou": self.iou,
            "f1_dice": self.f1_dice,
            "precision": self.precision,
            "recall": self.recall,
            "area_error_ratio": self.area_error_ratio,
            "brier_score": self.brier_score,
            "expected_calibration_error": self.expected_calibration_error,
        }

    def validate(self) -> None:
        for name, raw in self.as_dict().items():
            if raw is None:
                continue
            if isinstance(raw, bool) or not isinstance(raw, int | float) or not math.isfinite(raw):
                raise ContractError(f"Validation metric {name} must be finite or null.")
            if name == "area_error_ratio":
                if raw < 0:
                    raise ContractError("area_error_ratio must be non-negative.")
            elif not 0 <= raw <= 1:
                raise ContractError(f"Validation metric {name} must be between 0 and 1.")


@dataclass(frozen=True, slots=True)
class SpatialPartitionContract:
    """One committed train or holdout region in the target CRS."""

    spatial_group_id: str
    split: Literal["train", "holdout"]
    bounds: tuple[float, float, float, float]

    def validate(self) -> None:
        if not isinstance(self.spatial_group_id, str) or not self.spatial_group_id.strip():
            raise ContractError("Spatial partition IDs must be non-empty strings.")
        if self.split not in {"train", "holdout"}:
            raise ContractError("Spatial partition split must be train or holdout.")
        if not isinstance(self.bounds, tuple) or len(self.bounds) != 4:
            raise ContractError("Spatial partition bounds require four values.")
        left, bottom, right, top = self.bounds
        if any(
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(value)
            for value in self.bounds
        ) or not (left < right and bottom < top):
            raise ContractError("Spatial partition bounds must be finite and ordered.")


@dataclass(frozen=True, slots=True)
class GeoAIRunContract:
    """Immutable inputs, model identity, raster grid, and promotion gates."""

    run_id: str
    study_area: str
    run_status: Literal["blocked", "prepared", "running", "completed", "failed"]
    geoai_version: Literal["0.41.1"]
    geoai_commit: str
    model_id: str
    model_revision: str
    model_sha256: str | None
    architecture: Literal["unet", "fpn"]
    encoder: str
    encoder_weights: str | None
    preprocessing: PreprocessingContract
    channel_count: int
    encoded_feature_sha256: str
    reference_mask_sha256: str
    prepared_tile_manifest_sha256: str | None
    spatial_partitions: tuple[SpatialPartitionContract, ...]
    input_manifest_rows: tuple[InputManifestRow, ...]
    reference_mask_id: str
    reference_mask_status: str
    target_crs: str
    resolution: tuple[float, float]
    bounds: tuple[float, float, float, float]
    tile_size: int
    overlap: int
    stride: int
    batch_size: int
    device: Literal["cpu", "cuda", "mps"]
    flood_class_index: Literal[1]
    probability_threshold: float
    external_output_workspace: Path
    source_timestamp: str
    source_name: str
    data_version: str
    confidence_class: Literal["low", "medium", "high"]
    assumptions: tuple[str, ...]
    processing_scope: str
    processing_allowed: bool
    can_feed_decision_layer: bool
    reason_blocked: str
    validation_metrics: ValidationMetricsContract
    floodguard_commit: str
    official_warning: Literal[False] = False
    dataset_mode: Literal["candidate", "official_input"] = "candidate"
    operational_status: Literal[
        "non_operational",
        "planning_only",
        "agency_operational",
    ] = "non_operational"
    spatial_holdout_ids: tuple[str, ...] = field(default_factory=tuple)

    @property
    def input_manifest_sha256(self) -> str:
        """Return an order-independent canonical receipt for all input rows."""

        rows = [
            {
                "processing_allowed": row.processing_allowed,
                "product_id": row.product_id,
                "role": row.role,
                "sha256": row.sha256,
                "source_timestamp": row.source_timestamp,
            }
            for row in sorted(
                self.input_manifest_rows,
                key=lambda item: (item.role, item.product_id),
            )
        ]
        encoded = json.dumps(
            {"schema_version": "1.0", "rows": rows},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def training_lineage_receipts(self) -> dict[str, str]:
        """Return the canonical receipts that a packaged model must retain."""

        if self.prepared_tile_manifest_sha256 is None:
            raise ContractError("Training lineage requires a prepared tile manifest receipt.")
        return {
            "prepared_tile_manifest_sha256": self.prepared_tile_manifest_sha256,
            "preprocessing_sidecar_sha256": self.preprocessing.sidecar_sha256,
            "encoded_feature_stack_sha256": self.encoded_feature_sha256,
            "reference_mask_sha256": self.reference_mask_sha256,
            "input_manifest_sha256": self.input_manifest_sha256,
        }

    def validate(self) -> None:
        if not isinstance(self.run_status, str) or self.run_status not in {
            "blocked",
            "prepared",
            "running",
            "completed",
            "failed",
        }:
            raise ContractError("run_status is invalid.")
        if self.geoai_version != "0.41.1":
            raise ContractError("GeoAI package version must be 0.41.1.")
        if not isinstance(self.architecture, str) or self.architecture not in {
            "unet",
            "fpn",
        }:
            raise ContractError("Architecture must be unet or fpn.")
        if not isinstance(self.device, str) or self.device not in {"cpu", "cuda", "mps"}:
            raise ContractError("Device must be cpu, cuda, or mps.")
        if self.flood_class_index != 1 or type(self.flood_class_index) is not int:
            raise ContractError("Binary flood_class_index must be integer class 1.")
        if self.official_warning is not False:
            raise ContractError("GeoAI candidate output is not an official warning.")
        if not isinstance(self.dataset_mode, str) or self.dataset_mode not in {
            "candidate",
            "official_input",
        }:
            raise ContractError("dataset_mode is invalid.")
        if not isinstance(self.operational_status, str) or self.operational_status not in {
            "non_operational",
            "planning_only",
            "agency_operational",
        }:
            raise ContractError("operational_status is invalid.")
        if not isinstance(self.confidence_class, str) or self.confidence_class not in {
            "low",
            "medium",
            "high",
        }:
            raise ContractError("confidence_class is invalid.")
        required_text = (
            ("run_id", self.run_id),
            ("study_area", self.study_area),
            ("model_id", self.model_id),
            ("model_revision", self.model_revision),
            ("encoder", self.encoder),
            ("reference_mask_id", self.reference_mask_id),
            ("reference_mask_status", self.reference_mask_status),
            ("target_crs", self.target_crs),
            ("processing_scope", self.processing_scope),
            ("source_timestamp", self.source_timestamp),
            ("source_name", self.source_name),
            ("data_version", self.data_version),
        )
        for label, value in required_text:
            if not isinstance(value, str) or not value.strip():
                raise ContractError(f"{label} is required.")
        if not isinstance(self.reason_blocked, str):
            raise ContractError("reason_blocked must be a string.")
        if not isinstance(self.geoai_commit, str) or not COMMIT_RE.fullmatch(self.geoai_commit):
            raise ContractError("GeoAI source must be pinned to a 40-character commit.")
        if not isinstance(self.floodguard_commit, str) or not COMMIT_RE.fullmatch(
            self.floodguard_commit
        ):
            raise ContractError("FloodGuard commit must be a 40-character commit.")
        if self.model_sha256 is not None and (
            not isinstance(self.model_sha256, str) or not SHA256_RE.fullmatch(self.model_sha256)
        ):
            raise ContractError("Model checkpoint SHA-256 is required.")
        if self.encoder_weights is not None and (
            not isinstance(self.encoder_weights, str) or not self.encoder_weights.strip()
        ):
            raise ContractError("encoder_weights must be null or a non-empty string.")
        if self.run_status == "completed" and self.model_sha256 is None:
            raise ContractError("A completed run requires a model checkpoint SHA-256.")
        if (
            self.run_status in {"prepared", "running", "completed"}
            and self.prepared_tile_manifest_sha256 is None
        ):
            raise ContractError(
                "Prepared, running, and completed runs require a tile manifest receipt."
            )
        if not isinstance(self.preprocessing, PreprocessingContract):
            raise ContractError("preprocessing must be a PreprocessingContract.")
        self.preprocessing.validate()
        if (
            type(self.channel_count) is not int
            or not 6 <= self.channel_count <= 8
            or self.channel_count != len(self.preprocessing.channel_names)
        ):
            raise ContractError("channel_count must match the 6-8 ordered channel names.")
        for label, checksum in (
            ("encoded_feature_sha256", self.encoded_feature_sha256),
            ("reference_mask_sha256", self.reference_mask_sha256),
        ):
            if not isinstance(checksum, str) or not SHA256_RE.fullmatch(checksum):
                raise ContractError(f"{label} requires a lowercase SHA-256.")
        if self.prepared_tile_manifest_sha256 is not None and (
            not isinstance(self.prepared_tile_manifest_sha256, str)
            or not SHA256_RE.fullmatch(self.prepared_tile_manifest_sha256)
        ):
            raise ContractError(
                "prepared_tile_manifest_sha256 must be null or a lowercase SHA-256."
            )
        if not isinstance(self.validation_metrics, ValidationMetricsContract):
            raise ContractError("validation_metrics must use the typed metric contract.")
        self.validation_metrics.validate()
        if (
            not isinstance(self.input_manifest_rows, tuple)
            or not self.input_manifest_rows
            or any(not isinstance(row, InputManifestRow) for row in self.input_manifest_rows)
        ):
            raise ContractError("At least one immutable input manifest row is required.")
        for row in self.input_manifest_rows:
            row.validate()
        roles = [row.role for row in self.input_manifest_rows]
        if len(set(roles)) != len(roles):
            raise ContractError("Input manifest roles must be unique within a run.")
        product_ids = [row.product_id for row in self.input_manifest_rows]
        if len(set(product_ids)) != len(product_ids):
            raise ContractError("Input manifest product IDs must be unique within a run.")
        reference_rows = [row for row in self.input_manifest_rows if row.role == "reference_mask"]
        if len(reference_rows) != 1:
            raise ContractError("Exactly one reference_mask input row is required.")
        reference_row = reference_rows[0]
        if (
            reference_row.product_id != self.reference_mask_id
            or reference_row.sha256 != self.reference_mask_sha256
        ):
            raise ContractError(
                "The reference-mask ID and checksum must match its input manifest row."
            )
        source_time = _require_rfc3339(self.source_timestamp, "source_timestamp")
        if (
            not isinstance(self.assumptions, tuple)
            or not self.assumptions
            or any(not isinstance(item, str) or not item.strip() for item in self.assumptions)
        ):
            raise ContractError("At least one non-empty assumption is required.")
        if not re.fullmatch(r"EPSG:\d+", self.target_crs, re.IGNORECASE):
            raise ContractError("target_crs must be an explicit EPSG identifier.")
        if (
            not isinstance(self.resolution, tuple)
            or len(self.resolution) != 2
            or any(
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or not math.isfinite(value)
                or value <= 0
                for value in self.resolution
            )
        ):
            raise ContractError("Resolution values must be positive.")
        if not isinstance(self.bounds, tuple) or len(self.bounds) != 4:
            raise ContractError("Bounds must be ordered left, bottom, right, top.")
        left, bottom, right, top = self.bounds
        if any(
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(value)
            for value in self.bounds
        ) or not (left < right and bottom < top):
            raise ContractError("Bounds must be ordered left, bottom, right, top.")
        if (
            type(self.tile_size) is not int
            or type(self.overlap) is not int
            or self.tile_size <= 0
            or self.overlap < 0
            or self.overlap >= self.tile_size
        ):
            raise ContractError("Tile size and overlap are invalid.")
        if type(self.stride) is not int or self.stride != self.tile_size - self.overlap:
            raise ContractError("Stride must equal tile_size - overlap.")
        if (
            type(self.batch_size) is not int
            or self.batch_size <= 0
            or isinstance(self.probability_threshold, bool)
            or not isinstance(self.probability_threshold, int | float)
            or not math.isfinite(self.probability_threshold)
            or not 0 < self.probability_threshold < 1
        ):
            raise ContractError(
                "Batch size and probability threshold must be positive and bounded."
            )
        if not isinstance(self.external_output_workspace, Path) or not (
            self.external_output_workspace.is_absolute()
        ):
            raise ContractError("Large outputs must use an absolute external workspace.")
        if self.external_output_workspace == Path(self.external_output_workspace.anchor):
            raise ContractError("The filesystem root is not a valid output workspace.")
        strict_gates = (
            type(self.processing_allowed) is bool and type(self.can_feed_decision_layer) is bool
        )
        if not strict_gates:
            raise ContractError("Safety gates must be strict booleans.")
        all_inputs_allowed = all(row.processing_allowed for row in self.input_manifest_rows)
        if self.processing_allowed and not all_inputs_allowed:
            raise ContractError("processing_allowed cannot override a blocked input row.")
        rows_by_role = {row.role: row for row in self.input_manifest_rows}
        if self.processing_allowed:
            required_roles = _required_provenance_roles(self.preprocessing.channel_names)
            missing_roles = sorted(required_roles - set(rows_by_role))
            if missing_roles:
                raise ContractError(
                    "Processing requires provenance role(s): " + ", ".join(missing_roles)
                )
            pre_time = _require_rfc3339(
                rows_by_role["pre_event_sar"].source_timestamp,
                "pre_event_sar source_timestamp",
            )
            post_time = _require_rfc3339(
                rows_by_role["post_event_sar"].source_timestamp,
                "post_event_sar source_timestamp",
            )
            if not pre_time < post_time <= source_time:
                raise ContractError(
                    "Input timing must satisfy pre_event_sar < post_event_sar "
                    "<= run source_timestamp."
                )
        if self.processing_allowed and self.reference_mask_status != "confirmed_for_model_purpose":
            raise ContractError(
                "Processing requires a reference mask confirmed for this model purpose."
            )
        if (
            self.processing_allowed or self.run_status in {"prepared", "running", "completed"}
        ) and not self.spatial_holdout_ids:
            raise ContractError("Prepared GeoAI work requires an explicit spatial holdout.")
        invalid_holdouts = not isinstance(self.spatial_holdout_ids, tuple) or any(
            not isinstance(holdout_id, str) or not holdout_id.strip()
            for holdout_id in self.spatial_holdout_ids
        )
        if invalid_holdouts or len(set(self.spatial_holdout_ids)) != len(self.spatial_holdout_ids):
            raise ContractError("Spatial holdout IDs must be unique, non-empty strings.")
        self._validate_spatial_partitions()
        if self.can_feed_decision_layer:
            if self.dataset_mode != "official_input":
                raise ContractError("Candidate GeoAI runs cannot feed the decision layer.")
            if not self.processing_allowed or self.run_status != "completed":
                raise ContractError("Only a completed, processing-allowed run may feed decisions.")
            if self.confidence_class == "low":
                raise ContractError("Low-confidence output cannot feed the decision layer.")
            if self.operational_status == "non_operational":
                raise ContractError("Non-operational output cannot feed the decision layer.")
            if not self.validation_metrics.is_complete:
                raise ContractError(
                    "Decision-layer promotion requires complete validation metrics."
                )
        elif not self.reason_blocked.strip():
            raise ContractError("A non-feedable run requires reason_blocked.")

    def _validate_spatial_partitions(self) -> None:
        if not isinstance(self.spatial_partitions, tuple) or any(
            not isinstance(partition, SpatialPartitionContract)
            for partition in self.spatial_partitions
        ):
            raise ContractError("spatial_partitions must use the typed partition contract.")
        if not self.processing_allowed and self.run_status not in {
            "prepared",
            "running",
            "completed",
        }:
            return
        if not self.spatial_partitions:
            raise ContractError("Prepared GeoAI work requires committed spatial partitions.")
        for partition in self.spatial_partitions:
            partition.validate()
        group_ids = [partition.spatial_group_id for partition in self.spatial_partitions]
        if len(set(group_ids)) != len(group_ids):
            raise ContractError("Spatial partition IDs must be unique.")
        holdout_ids = {
            partition.spatial_group_id
            for partition in self.spatial_partitions
            if partition.split == "holdout"
        }
        if holdout_ids != set(self.spatial_holdout_ids):
            raise ContractError("spatial_holdout_ids must exactly match holdout partition IDs.")
        if not any(partition.split == "train" for partition in self.spatial_partitions):
            raise ContractError("At least one training spatial partition is required.")
        run_left, run_bottom, run_right, run_top = self.bounds
        for partition in self.spatial_partitions:
            left, bottom, right, top = partition.bounds
            if not (
                run_left <= left < right <= run_right and run_bottom <= bottom < top <= run_top
            ):
                raise ContractError("Spatial partitions must stay within the run bounds.")
        for index, first in enumerate(self.spatial_partitions):
            for second in self.spatial_partitions[index + 1 :]:
                if _bounds_have_interior_overlap(first.bounds, second.bounds):
                    raise ContractError("Spatial partition interiors must not overlap.")

    def public_dict(self) -> dict[str, object]:
        """Return a redacted manifest safe for Studio or API display."""

        self.validate()
        payload = asdict(self)
        payload["external_output_workspace"] = "external-workspace/" + self.run_id
        serialized = repr(payload)
        if PRIVATE_PATH_RE.search(serialized):
            raise ContractError("Public manifest contains a private absolute path.")
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> GeoAIRunContract:
        """Parse a JSON-compatible contract and reject unreviewed fields."""

        if not isinstance(payload, dict):
            raise ContractError("Run contract payload must be an object.")
        allowed = set(cls.__dataclass_fields__)
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise ContractError("Unknown run contract field(s): " + ", ".join(unknown))
        values = dict(payload)
        try:
            preprocessing = values["preprocessing"]
            manifest_rows = values["input_manifest_rows"]
            if not isinstance(preprocessing, dict) or not isinstance(manifest_rows, list):
                raise ContractError(
                    "preprocessing must be an object and input_manifest_rows an array."
                )
            values["preprocessing"] = PreprocessingContract(
                method=preprocessing["method"],
                channel_names=tuple(preprocessing["channel_names"]),
                transforms=tuple(
                    BandTransformContract(**transform) for transform in preprocessing["transforms"]
                ),
                sidecar_sha256=preprocessing["sidecar_sha256"],
                encoded_dtype=preprocessing.get("encoded_dtype", "uint8"),
                encoded_range=tuple(preprocessing.get("encoded_range", (0, 255))),
                stock_geoai_divisor=preprocessing.get("stock_geoai_divisor", 255),
            )
            values["input_manifest_rows"] = tuple(InputManifestRow(**row) for row in manifest_rows)
            values["spatial_partitions"] = tuple(
                SpatialPartitionContract(
                    spatial_group_id=partition["spatial_group_id"],
                    split=partition["split"],
                    bounds=tuple(partition["bounds"]),
                )
                for partition in values["spatial_partitions"]
            )
            values["validation_metrics"] = ValidationMetricsContract(**values["validation_metrics"])
            values["resolution"] = tuple(values["resolution"])
            values["bounds"] = tuple(values["bounds"])
            values["assumptions"] = tuple(values["assumptions"])
            values["spatial_holdout_ids"] = tuple(values.get("spatial_holdout_ids", ()))
            values["external_output_workspace"] = Path(values["external_output_workspace"])
            contract = cls(**values)
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, ContractError):
                raise
            raise ContractError(f"Malformed run contract: {exc}") from exc
        contract.validate()
        return contract

    @classmethod
    def from_json(cls, path: Path) -> GeoAIRunContract:
        """Load and validate a UTF-8 JSON run contract."""

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ContractError(f"Could not read run contract: {exc}") from exc
        return cls.from_dict(payload)


def _require_rfc3339(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{label} must be RFC 3339.") from exc
    if "T" not in value or parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractError(f"{label} must include a time and timezone.")
    return parsed


def _required_provenance_roles(channel_names: tuple[str, ...]) -> set[str]:
    required = {"pre_event_sar", "post_event_sar", "reference_mask"}
    sar_channels = {
        "pre_vv_db",
        "post_vv_db",
        "pre_vh_db",
        "post_vh_db",
        "vv_change_db",
        "vh_change_db",
    }
    for raw_name in channel_names:
        name = raw_name.casefold()
        if name in sar_channels:
            continue
        if "slope" in name:
            required.add("terrain_slope")
        elif "hand" in name:
            required.add("hand")
        elif "permanent_water" in name:
            required.add("permanent_water")
        else:
            raise ContractError(
                f"No explicit provenance role is defined for ancillary channel {raw_name!r}."
            )
    return required


def _bounds_have_interior_overlap(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> bool:
    return max(first[0], second[0]) < min(first[2], second[2]) and max(first[1], second[1]) < min(
        first[3], second[3]
    )
