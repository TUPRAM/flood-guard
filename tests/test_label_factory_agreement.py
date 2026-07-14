from __future__ import annotations

import pytest

from floodguard.label_factory.agreement import (
    AgreementError,
    compute_agreement,
    compute_boundary_f1,
)
from floodguard.label_factory.contracts import FloodLabel


def test_multiclass_agreement_reports_confusion_overlap_kappa_and_exclusions() -> None:
    reviewer_a = [
        [0, 1, 1],
        [0, 1, 2],
        [3, 4, 255],
    ]
    reviewer_b = [
        [0, 1, 0],
        [0, 1, 2],
        [3, 4, 255],
    ]

    report = compute_agreement(reviewer_a, reviewer_b, pixel_size_m=10)

    flood = report.class_metrics(FloodLabel.TEMPORARY_FLOOD)
    assert report.valid_pair_count == 8
    assert report.ignored_pair_count == 1
    assert report.confusion_for(FloodLabel.TEMPORARY_FLOOD, FloodLabel.DRY_LAND) == 1
    assert flood.iou == pytest.approx(2 / 3)
    assert flood.dice_f1 == pytest.approx(0.8)
    assert report.exact_agreement == pytest.approx(7 / 8)
    assert report.cohen_kappa == pytest.approx((0.875 - 15 / 64) / (1 - 15 / 64))
    assert report.binary_pair_count == 6
    assert report.temporary_flood_positive_agreement == pytest.approx(0.8)
    assert report.temporary_flood_area_difference_cells == -1
    assert report.temporary_flood_area_difference_square_m == -100


def test_identical_boundaries_score_one_and_tolerance_matches_one_cell_shift() -> None:
    reference = [
        [0, 0, 0, 0, 0],
        [0, 1, 1, 0, 0],
        [0, 1, 1, 0, 0],
        [0, 0, 0, 0, 0],
    ]
    shifted = [
        [0, 0, 0, 0, 0],
        [0, 0, 1, 1, 0],
        [0, 0, 1, 1, 0],
        [0, 0, 0, 0, 0],
    ]

    exact = compute_boundary_f1(reference, reference, tolerance_m=0, pixel_size_m=10)
    tolerant = compute_boundary_f1(reference, shifted, tolerance_m=10, pixel_size_m=10)
    strict = compute_boundary_f1(reference, shifted, tolerance_m=0, pixel_size_m=10)

    assert exact.f1 == 1.0
    assert tolerant.f1 == 1.0
    assert strict.f1 < tolerant.f1


def test_flat_agreement_has_no_boundary_metric() -> None:
    report = compute_agreement([0, 1, 2], [0, 1, 2], pixel_size_m=10)

    assert report.boundary is None
    assert report.cohen_kappa == 1.0


def test_agreement_rejects_shape_mismatch_and_unknown_classes() -> None:
    with pytest.raises(AgreementError, match="shapes must match"):
        compute_agreement([[0, 1]], [[0], [1]])
    with pytest.raises(AgreementError, match="Invalid reviewer_b label"):
        compute_agreement([0, 1], [0, 99])
