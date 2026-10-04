"""Small-grid checks for automated optical disagreement diagnostics."""

from __future__ import annotations

import numpy as np
import pytest

from floodguard.automated_optical_diagnostics import (
    _densest_chip,
    pair_codes,
    summarize_pairs,
)


def _bands(shape: tuple[int, int]) -> dict[str, np.ndarray]:
    return {
        "blue": np.full(shape, 0.12, dtype=np.float32),
        "green": np.full(shape, 0.20, dtype=np.float32),
        "red": np.full(shape, 0.11, dtype=np.float32),
        "nir": np.full(shape, 0.12, dtype=np.float32),
        "swir16": np.full(shape, 0.04, dtype=np.float32),
        "swir22": np.full(shape, 0.03, dtype=np.float32),
    }


def test_pair_codes_keep_all_four_pairs_and_exclude_unobservable() -> None:
    a = np.array([[0, 1, 0], [1, 1, 0]], dtype=bool)
    b = np.array([[0, 0, 1], [1, 0, 1]], dtype=bool)
    observable = np.array([[1, 1, 1], [1, 0, 0]], dtype=bool)
    assert pair_codes(a, b, observable).tolist() == [[0, 1, 2], [3, 255, 255]]
    with pytest.raises(ValueError, match="share"):
        pair_codes(a, b[:, :2], observable)
    with pytest.raises(ValueError, match="Boolean"):
        pair_codes(a.astype(np.uint8), b, observable)


def test_summary_reconciles_scl_and_spectral_predicates() -> None:
    pairs = np.array([[0, 1, 2], [3, 255, 2]], dtype=np.uint8)
    scl = np.array([[4, 5, 6], [7, 8, 6]], dtype=np.uint8)
    bands = _bands(pairs.shape)
    bands["swir16"][0, 1] = 0.30  # A-only fails the MNDWI threshold.
    result = summarize_pairs(pairs, scl, bands)
    assert result["pair_counts"] == {"neither": 1, "a_only": 1, "b_only": 2, "both": 1}
    assert result["comparable_cell_count"] == 5
    assert result["scl_counts_by_pair"]["b_only"] == {"6": 2}
    assert result["spectral_by_pair"]["a_only"]["predicate_fail_counts"]["mndwi_gt_0_1"] == 1
    assert result["nearby_20m"]["b_only_within_20m_of_a_water"] == 2
    assert result["nearby_20m"]["a_only_within_20m_of_b_water"] == 1


def test_summary_rejects_misaligned_scl() -> None:
    with pytest.raises(ValueError, match="must agree"):
        summarize_pairs(np.zeros((2, 2), dtype=np.uint8), np.zeros((1, 2)), _bands((2, 2)))
    with pytest.raises(ValueError, match="unexpected code"):
        summarize_pairs(np.full((2, 2), 5, dtype=np.uint8), np.zeros((2, 2)), _bands((2, 2)))


def test_densest_chip_is_deterministic_on_a_tied_grid() -> None:
    pairs = np.zeros((4, 5), dtype=np.uint8)
    pairs[0:2, 0:2] = 1
    pairs[2:4, 3:5] = 1
    assert _densest_chip(pairs, 1, 2) == (0, 0, 4)
    with pytest.raises(ValueError, match="larger"):
        _densest_chip(pairs, 1, 5)
