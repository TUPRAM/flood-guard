"""Core label-factory contracts and fail-closed safety semantics.

This module deliberately contains no geospatial or machine-learning runtime
dependencies.  It defines the meanings that rasterisation, annotation, and
model code must share before any reviewed labels can be used for training.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum, IntEnum


class LabelContractError(ValueError):
    """Raised when label-factory data violate a semantic contract."""


class FloodLabel(IntEnum):
    """Canonical stored label codes for the flood-label factory.

    Codes 0 through 4 describe an explicit human review outcome.  Code 255 is
    intentionally distinct: it means no review decision has been made.  In
    particular, unreviewed cells must never be interpreted as dry land.
    """

    DRY_LAND = 0
    TEMPORARY_FLOOD = 1
    PERMANENT_OR_PREEXISTING_WATER = 2
    UNCERTAIN_WATER_CHANGE = 3
    UNOBSERVABLE_OR_ARTIFACT = 4
    UNREVIEWED = 255

    @property
    def binary_temporary_flood_target(self) -> int | None:
        """Return the supervised binary target, or ``None`` when excluded.

        Permanent/pre-existing water is an explicit reviewed negative for the
        *temporary-flood* target, while uncertain, unobservable, and unreviewed
        cells cannot enter binary training.
        """

        if self is FloodLabel.TEMPORARY_FLOOD:
            return 1
        if self in {
            FloodLabel.DRY_LAND,
            FloodLabel.PERMANENT_OR_PREEXISTING_WATER,
        }:
            return 0
        return None

    @property
    def is_explicit_review_outcome(self) -> bool:
        """Return whether a reviewer explicitly assessed the cell."""

        return self is not FloodLabel.UNREVIEWED

    @property
    def is_binary_trainable(self) -> bool:
        """Return whether this class may enter the temporary-flood target."""

        return self.binary_temporary_flood_target is not None


class WeakSeedLabel(IntEnum):
    """Codes emitted when a legacy binary polygon becomes a weak seed.

    These names preserve provenance: a weak positive uses the same raster code
    as temporary flood, but it is not thereby promoted to reviewed truth.
    Downstream manifests must retain the weak-seed source type.
    """

    WEAK_POSITIVE = FloodLabel.TEMPORARY_FLOOD.value
    WEAK_UNCERTAIN = FloodLabel.UNCERTAIN_WATER_CHANGE.value
    UNREVIEWED = FloodLabel.UNREVIEWED.value


class DatasetRole(str, Enum):
    """Mutually exclusive roles assigned before label acquisition begins."""

    REVIEWER_CALIBRATION = "reviewer_calibration"
    TRAINING_AND_QUERY_POOL = "training_and_query_pool"
    FIXED_WITHIN_EVENT_DEVELOPMENT = "fixed_within_event_development"
    UNTOUCHED_GEOGRAPHIC_TEST = "untouched_geographic_test"

    @property
    def allows_active_selection(self) -> bool:
        """Return whether active learning may select from this role."""

        return self is DatasetRole.TRAINING_AND_QUERY_POOL

    @property
    def allows_query_model_training(self) -> bool:
        """Return whether reviewed labels may train a query model."""

        return self is DatasetRole.TRAINING_AND_QUERY_POOL

    @property
    def allows_threshold_or_model_selection(self) -> bool:
        """Return whether this role may tune model or threshold choices."""

        return self is DatasetRole.FIXED_WITHIN_EVENT_DEVELOPMENT

    @property
    def is_untouched_test(self) -> bool:
        """Return whether this role is isolated until the method is frozen."""

        return self is DatasetRole.UNTOUCHED_GEOGRAPHIC_TEST


class ModelPurpose(str, Enum):
    """Declared purpose of an ML artifact."""

    QUERY_RANKING = "query_ranking"
    FLOOD_ESTIMATION = "flood_estimation"


class HumanReviewedTrainingEligibility(str, Enum):
    """Whether an artifact may support training after human review."""

    NO = "no"
    CONDITIONAL = "conditional"
    YES = "yes"


@dataclass(frozen=True)
class ModelEligibility:
    """Fail-closed eligibility fields stored with every model artifact.

    Query-ranking models have a hard contract: they may rank a human-review
    queue and may contribute only after human review, but may never drive the
    decision layer, FPPS, or warnings.  Constructing contradictory flags raises
    immediately rather than relying on a downstream consumer to notice them.
    """

    purpose: ModelPurpose
    eligible_for_review_queue: bool
    eligible_for_training_after_human_review: HumanReviewedTrainingEligibility
    query_model_only: bool
    eligible_for_decision_layer: bool
    eligible_for_fpps: bool
    eligible_for_warning: bool

    def __post_init__(self) -> None:
        if not isinstance(self.purpose, ModelPurpose):
            raise LabelContractError("purpose must be a ModelPurpose value.")
        if not isinstance(
            self.eligible_for_training_after_human_review,
            HumanReviewedTrainingEligibility,
        ):
            raise LabelContractError(
                "eligible_for_training_after_human_review must use the declared enum."
            )
        boolean_fields = {
            "eligible_for_review_queue": self.eligible_for_review_queue,
            "query_model_only": self.query_model_only,
            "eligible_for_decision_layer": self.eligible_for_decision_layer,
            "eligible_for_fpps": self.eligible_for_fpps,
            "eligible_for_warning": self.eligible_for_warning,
        }
        invalid_boolean_fields = [
            name for name, value in boolean_fields.items() if not isinstance(value, bool)
        ]
        if invalid_boolean_fields:
            raise LabelContractError(
                "Eligibility fields must be booleans: "
                f"{', '.join(invalid_boolean_fields)}."
            )
        if self.purpose is ModelPurpose.QUERY_RANKING:
            required = (
                self.eligible_for_review_queue is True
                and self.eligible_for_training_after_human_review
                is HumanReviewedTrainingEligibility.CONDITIONAL
                and self.query_model_only is True
                and self.eligible_for_decision_layer is False
                and self.eligible_for_fpps is False
                and self.eligible_for_warning is False
            )
            if not required:
                raise LabelContractError(
                    "Query-ranking eligibility is fixed: review queue=true, "
                    "training after human review=conditional, query_model_only=true, "
                    "decision layer=false, FPPS=false, warning=false."
                )
        if self.query_model_only and (
            self.eligible_for_decision_layer
            or self.eligible_for_fpps
            or self.eligible_for_warning
        ):
            raise LabelContractError(
                "A query-model-only artifact cannot feed decisions, FPPS, or warnings."
            )
        if self.eligible_for_fpps and not self.eligible_for_decision_layer:
            raise LabelContractError(
                "FPPS eligibility requires separate decision-layer eligibility."
            )
        if self.eligible_for_warning and not self.eligible_for_decision_layer:
            raise LabelContractError(
                "Warning eligibility requires separate decision-layer eligibility."
            )

    def as_manifest_fields(self) -> dict[str, bool | str]:
        """Return stable scalar fields suitable for a CSV/JSON manifest."""

        return {
            "model_purpose": self.purpose.value,
            "eligible_for_review_queue": self.eligible_for_review_queue,
            "eligible_for_training_after_human_review": (
                self.eligible_for_training_after_human_review.value
            ),
            "query_model_only": self.query_model_only,
            "eligible_for_decision_layer": self.eligible_for_decision_layer,
            "eligible_for_fpps": self.eligible_for_fpps,
            "eligible_for_warning": self.eligible_for_warning,
        }


QUERY_MODEL_ELIGIBILITY = ModelEligibility(
    purpose=ModelPurpose.QUERY_RANKING,
    eligible_for_review_queue=True,
    eligible_for_training_after_human_review=(
        HumanReviewedTrainingEligibility.CONDITIONAL
    ),
    query_model_only=True,
    eligible_for_decision_layer=False,
    eligible_for_fpps=False,
    eligible_for_warning=False,
)


def coerce_flood_label(value: int | FloodLabel) -> FloodLabel:
    """Return a validated :class:`FloodLabel` from an integer code."""

    if isinstance(value, WeakSeedLabel):
        raise LabelContractError(
            "A weak-seed label is not reviewed truth; retain its provenance and "
            "handle qualified weak supervision explicitly."
        )
    if isinstance(value, bool):
        raise LabelContractError(f"Unknown flood-label code: {value!r}")
    try:
        return FloodLabel(value)
    except (TypeError, ValueError) as exc:
        raise LabelContractError(f"Unknown flood-label code: {value!r}") from exc


def binary_temporary_flood_target(value: int | FloodLabel) -> int | None:
    """Map a stored class to a safe binary target or an exclusion marker."""

    return coerce_flood_label(value).binary_temporary_flood_target


def require_binary_training_labels(
    values: Sequence[int | FloodLabel],
) -> tuple[int, ...]:
    """Return binary targets and reject uncertain/unobservable/unreviewed input.

    This helper is intentionally fail-closed.  Callers that need to filter a
    mixed raster must do so explicitly before invoking it, making exclusions
    visible in their own QA and manifests.
    """

    targets: list[int] = []
    excluded: list[int] = []
    for index, value in enumerate(values):
        target = binary_temporary_flood_target(value)
        if target is None:
            excluded.append(index)
        else:
            targets.append(target)
    if excluded:
        preview = ", ".join(str(index) for index in excluded[:10])
        suffix = "..." if len(excluded) > 10 else ""
        raise LabelContractError(
            "Binary training input contains excluded label classes at indices "
            f"{preview}{suffix}."
        )
    return tuple(targets)


def convert_weak_binary_mask_to_positive_unlabeled(
    mask: Sequence[Sequence[int | bool]],
    *,
    boundary_buffer_cells: int = 0,
) -> tuple[tuple[WeakSeedLabel, ...], ...]:
    """Convert a legacy 0/1 weak mask into positive-unlabeled semantics.

    Legacy ``1`` cells become :class:`WeakSeedLabel.WEAK_POSITIVE`; legacy
    ``0`` cells become :class:`WeakSeedLabel.UNREVIEWED`, never dry land.  When
    ``boundary_buffer_cells`` is positive, cells on both sides of a local
    positive/unlabeled transition become weak-uncertain.  The buffer uses
    Chebyshev cell distance so diagonal polygon edges are treated consistently.

    The returned immutable integer grid is deterministic and dependency-free.
    It is a weak seed for review or explicitly qualified weak supervision, not
    reviewed validation truth.
    """

    if isinstance(boundary_buffer_cells, bool) or not isinstance(
        boundary_buffer_cells, int
    ):
        raise LabelContractError("boundary_buffer_cells must be an integer.")
    if boundary_buffer_cells < 0:
        raise LabelContractError("boundary_buffer_cells must be non-negative.")
    if not mask:
        raise LabelContractError("Weak mask must contain at least one row.")

    width = len(mask[0])
    if width == 0:
        raise LabelContractError("Weak mask rows must contain at least one cell.")

    normalized: list[list[int]] = []
    for row_index, row in enumerate(mask):
        if len(row) != width:
            raise LabelContractError(
                "Weak mask must be rectangular; "
                f"row {row_index} has {len(row)} cells instead of {width}."
            )
        normalized_row: list[int] = []
        for column_index, value in enumerate(row):
            if isinstance(value, bool):
                normalized_row.append(int(value))
            elif isinstance(value, int) and value in {0, 1}:
                normalized_row.append(value)
            else:
                raise LabelContractError(
                    "Weak mask values must be binary integers or booleans; "
                    f"found {value!r} at row {row_index}, column {column_index}."
                )
        normalized.append(normalized_row)

    output: list[list[WeakSeedLabel]] = [
        [
            WeakSeedLabel.WEAK_POSITIVE
            if value == 1
            else WeakSeedLabel.UNREVIEWED
            for value in row
        ]
        for row in normalized
    ]
    if boundary_buffer_cells == 0:
        return tuple(tuple(row) for row in output)

    height = len(normalized)
    for row_index in range(height):
        for column_index in range(width):
            value = normalized[row_index][column_index]
            if _has_opposite_within_buffer(
                normalized,
                row_index=row_index,
                column_index=column_index,
                value=value,
                radius=boundary_buffer_cells,
            ):
                output[row_index][column_index] = WeakSeedLabel.WEAK_UNCERTAIN

    return tuple(tuple(row) for row in output)


def _has_opposite_within_buffer(
    mask: list[list[int]],
    *,
    row_index: int,
    column_index: int,
    value: int,
    radius: int,
) -> bool:
    row_start = max(0, row_index - radius)
    row_stop = min(len(mask), row_index + radius + 1)
    column_start = max(0, column_index - radius)
    column_stop = min(len(mask[0]), column_index + radius + 1)
    return any(
        mask[other_row][other_column] != value
        for other_row in range(row_start, row_stop)
        for other_column in range(column_start, column_stop)
    )
