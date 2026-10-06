"""Dry-context comparison checks for the Mae Sai v2 development diagnostic."""

from __future__ import annotations

import numpy as np
import pytest

from floodguard.automated_optical_v2_diagnostics import summarize_dry_change


def test_dry_change_reconciles_observable_pairs_and_index_deltas() -> None:
    event = np.array([[0, 1, 2, 3], [2, 255, 2, 0]], dtype=np.uint8)
    dry = np.array([[0, 0, 0, 3], [2, 0, 255, 255]], dtype=np.uint8)
    green_event = np.full(event.shape, 0.2, dtype=np.float32)
    swir_event = np.full(event.shape, 0.1, dtype=np.float32)
    green_dry = np.full(event.shape, 0.1, dtype=np.float32)
    swir_dry = np.full(event.shape, 0.2, dtype=np.float32)
    result = summarize_dry_change(event, dry, green_event, swir_event, green_dry, swir_dry)
    assert result["b_only"]["event_cells"] == 3
    assert result["b_only"]["dry_observable_cells"] == 2
    assert result["b_only"]["dry_pair_counts"] == {
        "neither": 1, "a_only": 0, "b_only": 1, "both": 0,
    }
    assert result["b_only"]["delta_mndwi_event_minus_dry"]["median"] == pytest.approx(2 / 3)
    assert result["b_only"]["delta_swir16_event_minus_dry"]["median"] == pytest.approx(-0.1)
    assert result["a_only"]["dry_observable_cells"] == 1


def test_dry_change_rejects_misaligned_or_invalid_pairs() -> None:
    pair = np.zeros((2, 2), dtype=np.uint8)
    band = np.ones((2, 2), dtype=np.float32)
    with pytest.raises(ValueError, match="one shape"):
        summarize_dry_change(pair, pair[:, :1], band, band, band, band)
    invalid = np.full_like(pair, 7)
    with pytest.raises(ValueError, match="unexpected code"):
        summarize_dry_change(invalid, pair, band, band, band, band)
