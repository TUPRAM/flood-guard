from __future__ import annotations

import numpy as np
import pytest

from floodguard.geoid_radar_benchmark import predict_s1grd_sigma0


def _paired_tiles() -> tuple[np.ndarray, np.ndarray]:
    pre = np.full((2, 256, 256), 0.1, dtype="float32")
    post = pre.copy()
    post[:, :128, :] = 0.01
    return pre, post


@pytest.mark.parametrize(
    ("pre_shape", "post_shape"),
    [((256, 256), (256, 256)), ((1, 256, 256), (1, 256, 256)),
     ((2, 256, 256), (2, 255, 256)), ((2, 0, 256), (2, 0, 256))],
)
def test_rejects_incompatible_tile_shapes(
    pre_shape: tuple[int, ...], post_shape: tuple[int, ...]
) -> None:
    with pytest.raises(ValueError, match="shape"):
        predict_s1grd_sigma0(np.ones(pre_shape), np.ones(post_shape))


def test_positive_negative_darkening_gates_and_invalid_radiometry() -> None:
    pre, post = _paired_tiles()
    post[1, 0, 0] = pre[1, 0, 0]  # VV-only darkening is not a candidate.
    post[0, 0, 1] = pre[0, 0, 1]  # VH-only darkening is not a candidate.
    pre[0, 0, 2] = np.nan
    pre[1, 0, 3] = np.inf
    post[0, 0, 4] = 0
    post[1, 0, 5] = -1

    candidate, summary = predict_s1grd_sigma0(pre, post)

    assert candidate.dtype == np.uint8
    assert candidate[20, 20] == 1
    assert candidate[200, 20] == 0
    assert candidate[0, 0] == 0
    assert candidate[0, 1] == 0
    assert np.array_equal(candidate[0, 2:6], np.full(4, 255, dtype="uint8"))
    assert summary["source_valid_cells"] == 256**2 - 4
    assert summary["source_invalid_cells"] == 4
    assert summary["histogram_abstained_cells"] == 0
    assert summary["qualified_windows"] == 1
    assert summary["total_windows"] == 1
    assert summary["candidate_cells"] > 0
    assert summary["classified_non_candidate_cells"] > 0


def test_all_windows_abstain_without_reporting_zero_flood() -> None:
    pre = np.full((2, 256, 256), 0.1, dtype="float32")
    post = pre.copy()

    candidate, summary = predict_s1grd_sigma0(pre, post)

    assert np.all(candidate == 255)
    assert summary["source_valid_cells"] == 256**2
    assert summary["histogram_abstained_cells"] == 256**2
    assert summary["qualified_windows"] == 0
    assert summary["total_windows"] == 1
    assert summary["reason_counts"] == {"narrow_or_invalid_distribution": 1}
    assert summary["result_status"] == "abstained_no_classified_cells"


def test_frozen_m2_parameters_and_window_placement() -> None:
    pre = np.full((2, 384, 384), 0.1, dtype="float32")
    post = pre.copy()
    post[:, :192, :] = 0.01

    _, summary = predict_s1grd_sigma0(pre, post)

    assert summary["configuration"] == {
        "window_pixels": 256,
        "stride_pixels": 128,
        "min_valid_samples": 4096,
        "histogram_bins": 64,
        "min_class_fraction": 0.08,
        "min_mean_separation_db": 1.5,
        "min_between_variance_fraction": 0.72,
    }
    assert summary["total_windows"] == 4
    assert {(row["row"], row["column"]) for row in summary["window_receipts"]} == {
        (0, 0), (0, 128), (128, 0), (128, 128)
    }
