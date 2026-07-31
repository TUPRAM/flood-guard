"""Reviewer-agreement metrics for canonical label rasters.

The functions in this module are intentionally dependency-light.  They operate
on flat sequences or rectangular two-dimensional sequences and report
multiclass overlap, chance-adjusted agreement, binary flood agreement, and a
spatial boundary score when a two-dimensional grid is available.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable, Sequence

from floodguard.label_factory.annotations import (
    BINARY_TARGET_BY_CLASS,
    LabelClass,
    coerce_label_class,
)


class AgreementError(ValueError):
    """Raised when reviewer rasters cannot be compared safely."""


DEFAULT_AGREEMENT_LABELS: tuple[LabelClass, ...] = (
    LabelClass.DRY_LAND,
    LabelClass.TEMPORARY_FLOOD,
    LabelClass.PERMANENT_OR_PREEXISTING_WATER,
    LabelClass.UNCERTAIN_WATER_CHANGE,
    LabelClass.UNOBSERVABLE_OR_ARTIFACT,
)


@dataclass(frozen=True, slots=True)
class ClassAgreement:
    """Overlap metrics for one class, treating reviewer A as the reference row."""

    label: LabelClass
    reviewer_a_count: int
    reviewer_b_count: int
    intersection_count: int
    union_count: int
    iou: float | None
    dice_f1: float | None


@dataclass(frozen=True, slots=True)
class BoundaryAgreement:
    """Tolerance-based boundary precision, recall, and F1."""

    target_label: LabelClass
    tolerance_m: float
    tolerance_pixels: int
    reviewer_a_boundary_count: int
    reviewer_b_boundary_count: int
    precision: float
    recall: float
    f1: float


@dataclass(frozen=True, slots=True)
class AgreementReport:
    """Complete agreement result for a pair of reviewer rasters."""

    labels: tuple[LabelClass, ...]
    confusion_matrix: tuple[tuple[int, ...], ...]
    per_class: tuple[ClassAgreement, ...]
    valid_pair_count: int
    ignored_pair_count: int
    exact_agreement: float
    cohen_kappa: float
    binary_pair_count: int
    temporary_flood_positive_agreement: float | None
    temporary_flood_negative_agreement: float | None
    reviewer_a_temporary_flood_count: int
    reviewer_b_temporary_flood_count: int
    temporary_flood_area_difference_cells: int
    temporary_flood_area_difference_square_m: float | None
    uncertain_or_unobservable_coverage_difference_cells: int
    boundary: BoundaryAgreement | None

    def class_metrics(self, label: LabelClass | int | str) -> ClassAgreement:
        """Return overlap metrics for a named or coded class."""

        wanted = coerce_label_class(label)
        for metric in self.per_class:
            if metric.label is wanted:
                return metric
        raise KeyError(f"Label {int(wanted)} was not included in this report.")

    def confusion_for(
        self,
        reviewer_a_label: LabelClass | int | str,
        reviewer_b_label: LabelClass | int | str,
    ) -> int:
        """Return a single confusion-matrix cell."""

        a_label = coerce_label_class(reviewer_a_label)
        b_label = coerce_label_class(reviewer_b_label)
        try:
            a_index = self.labels.index(a_label)
            b_index = self.labels.index(b_label)
        except ValueError as exc:
            raise KeyError("Requested label was not included in this report.") from exc
        return self.confusion_matrix[a_index][b_index]

    def to_dict(self) -> dict[str, Any]:
        """Serialize metrics with stable numeric class-code keys."""

        return {
            "labels": [int(label) for label in self.labels],
            "confusion_matrix": [list(row) for row in self.confusion_matrix],
            "per_class": {
                str(int(metric.label)): {
                    "class_name": metric.label.name.lower(),
                    "reviewer_a_count": metric.reviewer_a_count,
                    "reviewer_b_count": metric.reviewer_b_count,
                    "intersection_count": metric.intersection_count,
                    "union_count": metric.union_count,
                    "iou": metric.iou,
                    "dice_f1": metric.dice_f1,
                }
                for metric in self.per_class
            },
            "valid_pair_count": self.valid_pair_count,
            "ignored_pair_count": self.ignored_pair_count,
            "exact_agreement": self.exact_agreement,
            "cohen_kappa": self.cohen_kappa,
            "binary_pair_count": self.binary_pair_count,
            "temporary_flood_positive_agreement": (
                self.temporary_flood_positive_agreement
            ),
            "temporary_flood_negative_agreement": (
                self.temporary_flood_negative_agreement
            ),
            "reviewer_a_temporary_flood_count": (
                self.reviewer_a_temporary_flood_count
            ),
            "reviewer_b_temporary_flood_count": (
                self.reviewer_b_temporary_flood_count
            ),
            "temporary_flood_area_difference_cells": (
                self.temporary_flood_area_difference_cells
            ),
            "temporary_flood_area_difference_square_m": (
                self.temporary_flood_area_difference_square_m
            ),
            "uncertain_or_unobservable_coverage_difference_cells": (
                self.uncertain_or_unobservable_coverage_difference_cells
            ),
            "boundary": (
                {
                    "target_label": int(self.boundary.target_label),
                    "tolerance_m": self.boundary.tolerance_m,
                    "tolerance_pixels": self.boundary.tolerance_pixels,
                    "reviewer_a_boundary_count": (
                        self.boundary.reviewer_a_boundary_count
                    ),
                    "reviewer_b_boundary_count": (
                        self.boundary.reviewer_b_boundary_count
                    ),
                    "precision": self.boundary.precision,
                    "recall": self.boundary.recall,
                    "f1": self.boundary.f1,
                }
                if self.boundary is not None
                else None
            ),
        }


def compute_agreement(
    reviewer_a: Sequence[Any],
    reviewer_b: Sequence[Any],
    *,
    labels: Iterable[LabelClass | int | str] = DEFAULT_AGREEMENT_LABELS,
    ignore_labels: Iterable[LabelClass | int | str] = (LabelClass.UNREVIEWED,),
    pixel_size_m: float | None = None,
    boundary_tolerance_m: float = 20.0,
) -> AgreementReport:
    """Compute multiclass and binary agreement for two reviewer rasters.

    A pair is ignored from multiclass statistics when either reviewer used an
    ignored class.  Binary flood agreement is stricter: a pair contributes only
    when both labels have an explicit binary interpretation (dry land,
    temporary flood, or permanent/pre-existing water).

    Boundary F1 is returned only for rectangular two-dimensional inputs and a
    positive ``pixel_size_m``.
    """

    a_flat, a_shape = _flatten_grid(reviewer_a, "reviewer_a")
    b_flat, b_shape = _flatten_grid(reviewer_b, "reviewer_b")
    if a_shape != b_shape:
        raise AgreementError(
            f"Reviewer raster shapes must match; received {a_shape} and {b_shape}."
        )
    if len(a_flat) != len(b_flat):
        raise AgreementError("Reviewer rasters must contain the same number of cells.")

    included_labels = _coerce_unique_labels(labels, "labels")
    if not included_labels:
        raise AgreementError("At least one agreement label is required.")
    ignored = set(_coerce_unique_labels(ignore_labels, "ignore_labels"))
    overlap = set(included_labels) & ignored
    if overlap:
        raise AgreementError(
            "labels and ignore_labels must not overlap: "
            + ", ".join(str(int(label)) for label in sorted(overlap, key=int))
        )

    a_values = tuple(_coerce_grid_label(value, "reviewer_a") for value in a_flat)
    b_values = tuple(_coerce_grid_label(value, "reviewer_b") for value in b_flat)
    label_index = {label: index for index, label in enumerate(included_labels)}
    matrix = [
        [0 for _ in included_labels]
        for _ in included_labels
    ]
    valid_pairs: list[tuple[LabelClass, LabelClass]] = []
    ignored_pair_count = 0
    for a_value, b_value in zip(a_values, b_values):
        if a_value in ignored or b_value in ignored:
            ignored_pair_count += 1
            continue
        if a_value not in label_index or b_value not in label_index:
            raise AgreementError(
                "Encountered a non-ignored class that was not included in labels: "
                f"{int(a_value)} vs {int(b_value)}."
            )
        matrix[label_index[a_value]][label_index[b_value]] += 1
        valid_pairs.append((a_value, b_value))

    valid_pair_count = len(valid_pairs)
    if valid_pair_count == 0:
        raise AgreementError("No comparable reviewer cells remain after exclusions.")

    per_class = tuple(
        _class_agreement(matrix, index, label)
        for index, label in enumerate(included_labels)
    )
    diagonal = sum(matrix[index][index] for index in range(len(included_labels)))
    exact_agreement = diagonal / valid_pair_count
    row_totals = [sum(row) for row in matrix]
    column_totals = [
        sum(matrix[row][column] for row in range(len(matrix)))
        for column in range(len(matrix))
    ]
    expected_agreement = sum(
        row * column for row, column in zip(row_totals, column_totals)
    ) / (valid_pair_count * valid_pair_count)
    if math.isclose(expected_agreement, 1.0):
        cohen_kappa = 1.0 if math.isclose(exact_agreement, 1.0) else 0.0
    else:
        cohen_kappa = (exact_agreement - expected_agreement) / (
            1.0 - expected_agreement
        )

    binary_pairs = [
        (BINARY_TARGET_BY_CLASS[a_value], BINARY_TARGET_BY_CLASS[b_value])
        for a_value, b_value in valid_pairs
        if a_value in BINARY_TARGET_BY_CLASS and b_value in BINARY_TARGET_BY_CLASS
    ]
    positive_agreement, negative_agreement = _binary_specific_agreement(binary_pairs)
    a_flood_count = sum(a_value for a_value, _ in binary_pairs)
    b_flood_count = sum(b_value for _, b_value in binary_pairs)
    area_difference_cells = b_flood_count - a_flood_count
    area_difference_square_m = (
        area_difference_cells * pixel_size_m * pixel_size_m
        if pixel_size_m is not None and pixel_size_m > 0
        else None
    )

    ambiguous = {
        LabelClass.UNCERTAIN_WATER_CHANGE,
        LabelClass.UNOBSERVABLE_OR_ARTIFACT,
    }
    a_ambiguous_count = sum(a_value in ambiguous for a_value, _ in valid_pairs)
    b_ambiguous_count = sum(b_value in ambiguous for _, b_value in valid_pairs)

    boundary: BoundaryAgreement | None = None
    if len(a_shape) == 2 and pixel_size_m is not None:
        boundary = compute_boundary_f1(
            reviewer_a,
            reviewer_b,
            target_label=LabelClass.TEMPORARY_FLOOD,
            ignore_labels=(
                LabelClass.UNCERTAIN_WATER_CHANGE,
                LabelClass.UNOBSERVABLE_OR_ARTIFACT,
                LabelClass.UNREVIEWED,
            ),
            pixel_size_m=pixel_size_m,
            tolerance_m=boundary_tolerance_m,
        )

    return AgreementReport(
        labels=included_labels,
        confusion_matrix=tuple(tuple(row) for row in matrix),
        per_class=per_class,
        valid_pair_count=valid_pair_count,
        ignored_pair_count=ignored_pair_count,
        exact_agreement=exact_agreement,
        cohen_kappa=cohen_kappa,
        binary_pair_count=len(binary_pairs),
        temporary_flood_positive_agreement=positive_agreement,
        temporary_flood_negative_agreement=negative_agreement,
        reviewer_a_temporary_flood_count=a_flood_count,
        reviewer_b_temporary_flood_count=b_flood_count,
        temporary_flood_area_difference_cells=area_difference_cells,
        temporary_flood_area_difference_square_m=area_difference_square_m,
        uncertain_or_unobservable_coverage_difference_cells=(
            b_ambiguous_count - a_ambiguous_count
        ),
        boundary=boundary,
    )


def compute_boundary_f1(
    reviewer_a: Sequence[Any],
    reviewer_b: Sequence[Any],
    *,
    target_label: LabelClass | int | str = LabelClass.TEMPORARY_FLOOD,
    ignore_labels: Iterable[LabelClass | int | str] = (
        LabelClass.UNCERTAIN_WATER_CHANGE,
        LabelClass.UNOBSERVABLE_OR_ARTIFACT,
        LabelClass.UNREVIEWED,
    ),
    pixel_size_m: float = 10.0,
    tolerance_m: float = 20.0,
) -> BoundaryAgreement:
    """Compute symmetric tolerance-based boundary agreement on a 2D grid."""

    if pixel_size_m <= 0 or not math.isfinite(pixel_size_m):
        raise AgreementError("pixel_size_m must be finite and greater than zero.")
    if tolerance_m < 0 or not math.isfinite(tolerance_m):
        raise AgreementError("tolerance_m must be finite and non-negative.")

    a_flat, a_shape = _flatten_grid(reviewer_a, "reviewer_a")
    b_flat, b_shape = _flatten_grid(reviewer_b, "reviewer_b")
    if len(a_shape) != 2 or len(b_shape) != 2:
        raise AgreementError("Boundary F1 requires rectangular 2D reviewer grids.")
    if a_shape != b_shape:
        raise AgreementError(
            f"Reviewer raster shapes must match; received {a_shape} and {b_shape}."
        )

    rows, columns = a_shape
    a_values = tuple(_coerce_grid_label(value, "reviewer_a") for value in a_flat)
    b_values = tuple(_coerce_grid_label(value, "reviewer_b") for value in b_flat)
    target = coerce_label_class(target_label)
    ignored = set(_coerce_unique_labels(ignore_labels, "ignore_labels"))
    valid = tuple(
        a_value not in ignored and b_value not in ignored
        for a_value, b_value in zip(a_values, b_values)
    )
    a_boundary = _boundary_points(a_values, valid, rows, columns, target)
    b_boundary = _boundary_points(b_values, valid, rows, columns, target)
    tolerance_pixels = int(math.ceil(tolerance_m / pixel_size_m))

    if not a_boundary and not b_boundary:
        precision = recall = f1 = 1.0
    elif not a_boundary or not b_boundary:
        precision = recall = f1 = 0.0
    else:
        precision = _matched_fraction(b_boundary, a_boundary, tolerance_pixels)
        recall = _matched_fraction(a_boundary, b_boundary, tolerance_pixels)
        f1 = (
            2.0 * precision * recall / (precision + recall)
            if precision + recall > 0
            else 0.0
        )

    return BoundaryAgreement(
        target_label=target,
        tolerance_m=float(tolerance_m),
        tolerance_pixels=tolerance_pixels,
        reviewer_a_boundary_count=len(a_boundary),
        reviewer_b_boundary_count=len(b_boundary),
        precision=precision,
        recall=recall,
        f1=f1,
    )


def _class_agreement(
    matrix: Sequence[Sequence[int]],
    index: int,
    label: LabelClass,
) -> ClassAgreement:
    reviewer_a_count = sum(matrix[index])
    reviewer_b_count = sum(row[index] for row in matrix)
    intersection = matrix[index][index]
    union = reviewer_a_count + reviewer_b_count - intersection
    denominator = reviewer_a_count + reviewer_b_count
    return ClassAgreement(
        label=label,
        reviewer_a_count=reviewer_a_count,
        reviewer_b_count=reviewer_b_count,
        intersection_count=intersection,
        union_count=union,
        iou=(intersection / union if union > 0 else None),
        dice_f1=(2.0 * intersection / denominator if denominator > 0 else None),
    )


def _binary_specific_agreement(
    pairs: Sequence[tuple[int, int]],
) -> tuple[float | None, float | None]:
    if not pairs:
        return None, None
    both_positive = sum(a == 1 and b == 1 for a, b in pairs)
    both_negative = sum(a == 0 and b == 0 for a, b in pairs)
    a_positive = sum(a == 1 for a, _ in pairs)
    b_positive = sum(b == 1 for _, b in pairs)
    a_negative = len(pairs) - a_positive
    b_negative = len(pairs) - b_positive
    positive_denominator = a_positive + b_positive
    negative_denominator = a_negative + b_negative
    return (
        (
            2.0 * both_positive / positive_denominator
            if positive_denominator > 0
            else None
        ),
        (
            2.0 * both_negative / negative_denominator
            if negative_denominator > 0
            else None
        ),
    )


def _boundary_points(
    values: Sequence[LabelClass],
    valid: Sequence[bool],
    rows: int,
    columns: int,
    target: LabelClass,
) -> set[tuple[int, int]]:
    points: set[tuple[int, int]] = set()
    for row in range(rows):
        for column in range(columns):
            index = row * columns + column
            if not valid[index] or values[index] is not target:
                continue
            for d_row, d_column in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                neighbor_row = row + d_row
                neighbor_column = column + d_column
                if not (0 <= neighbor_row < rows and 0 <= neighbor_column < columns):
                    continue
                neighbor = neighbor_row * columns + neighbor_column
                if valid[neighbor] and values[neighbor] is not target:
                    points.add((row, column))
                    break
    return points


def _matched_fraction(
    source: set[tuple[int, int]],
    target: set[tuple[int, int]],
    tolerance_pixels: int,
) -> float:
    tolerance_squared = tolerance_pixels * tolerance_pixels
    matched = 0
    for source_row, source_column in source:
        if any(
            (source_row - target_row) ** 2 + (source_column - target_column) ** 2
            <= tolerance_squared
            for target_row, target_column in target
        ):
            matched += 1
    return matched / len(source)


def _flatten_grid(
    values: Sequence[Any],
    name: str,
) -> tuple[tuple[Any, ...], tuple[int, ...]]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise AgreementError(f"{name} must be a sequence.")
    if len(values) == 0:
        raise AgreementError(f"{name} must not be empty.")

    first = values[0]
    if isinstance(first, Sequence) and not isinstance(first, (str, bytes)):
        rows: list[Sequence[Any]] = []
        expected_columns: int | None = None
        for row in values:
            if not isinstance(row, Sequence) or isinstance(row, (str, bytes)):
                raise AgreementError(f"{name} mixes flat and nested values.")
            if expected_columns is None:
                expected_columns = len(row)
                if expected_columns == 0:
                    raise AgreementError(f"{name} contains an empty row.")
            elif len(row) != expected_columns:
                raise AgreementError(f"{name} must be a rectangular grid.")
            rows.append(row)
        flattened = tuple(value for row in rows for value in row)
        return flattened, (len(rows), expected_columns or 0)

    if any(
        isinstance(value, Sequence) and not isinstance(value, (str, bytes))
        for value in values
    ):
        raise AgreementError(f"{name} mixes flat and nested values.")
    return tuple(values), (len(values),)


def _coerce_grid_label(value: Any, name: str) -> LabelClass:
    try:
        return coerce_label_class(value)
    except ValueError as exc:
        raise AgreementError(f"Invalid {name} label {value!r}.") from exc


def _coerce_unique_labels(
    values: Iterable[LabelClass | int | str],
    name: str,
) -> tuple[LabelClass, ...]:
    result: list[LabelClass] = []
    for value in values:
        try:
            label = coerce_label_class(value)
        except ValueError as exc:
            raise AgreementError(f"Invalid {name} value {value!r}.") from exc
        if label in result:
            raise AgreementError(f"{name} contains duplicate class {int(label)}.")
        result.append(label)
    return tuple(result)
