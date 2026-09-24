"""Frozen M2 decision rule adapted to GEOID-Flood linear Sigma0 S1GRD tiles.

This is a research-only radar adapter. It does not reproduce the Mae Sai
Gamma0 terrain correction or its permanent-water and terrain masks.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from typing import Any

import numpy as np

from floodguard.label_factory.sentinel1_processing import (
    AdaptiveOtsuConfig,
    _otsu_threshold,
    _window_starts,
)


def predict_s1grd_sigma0(
    pre: np.ndarray, post: np.ndarray
) -> tuple[np.ndarray, dict[str, Any]]:
    """Classify paired linear Sigma0 VV/VH tiles without reference information.

    Both arrays must have shape ``(2, height, width)`` with VV before VH.
    Pixels with any non-finite or non-positive source value abstain. The
    returned ``uint8`` codes are 0 (non-candidate), 1 (candidate), and 255
    (abstained). Histogram parameters and darkening gates are frozen to M2.
    """

    pre_values = np.asarray(pre)
    post_values = np.asarray(post)
    if (
        pre_values.ndim != 3
        or pre_values.shape[0] != 2
        or pre_values.shape[1] < 1
        or pre_values.shape[2] < 1
        or post_values.shape != pre_values.shape
        or not np.issubdtype(pre_values.dtype, np.number)
        or not np.issubdtype(post_values.dtype, np.number)
        or np.issubdtype(pre_values.dtype, np.complexfloating)
        or np.issubdtype(post_values.dtype, np.complexfloating)
    ):
        raise ValueError("pre and post must be real numeric arrays of shape (2, H, W)")

    # Float32 matches the source M2 change arithmetic. Overflowed source values
    # join the unsupported radiometry mask rather than entering a histogram.
    with np.errstate(over="ignore", invalid="ignore"):
        pre_linear = pre_values.astype("float32")
        post_linear = post_values.astype("float32")
    source_valid = np.all(
        np.isfinite(pre_linear)
        & np.isfinite(post_linear)
        & (pre_linear > 0)
        & (post_linear > 0),
        axis=0,
    )
    height, width = source_valid.shape
    pre_db = np.full(pre_linear.shape, np.nan, dtype="float32")
    post_db = np.full(post_linear.shape, np.nan, dtype="float32")
    with np.errstate(divide="ignore", invalid="ignore"):
        pre_db[:, source_valid] = np.float32(10) * np.log10(
            pre_linear[:, source_valid]
        )
        post_db[:, source_valid] = np.float32(10) * np.log10(
            post_linear[:, source_valid]
        )
    vv_change = pre_db[0] - post_db[0]
    vh_change = pre_db[1] - post_db[1]
    change = np.float32(0.4) * vv_change + np.float32(0.6) * vh_change

    parameters = AdaptiveOtsuConfig()
    threshold_sum = np.zeros((height, width), dtype="float64")
    threshold_count = np.zeros((height, width), dtype="uint16")
    window_receipts: list[dict[str, Any]] = []
    for row in _window_starts(height, parameters.window_pixels, parameters.stride_pixels):
        row_end = min(row + parameters.window_pixels, height)
        for column in _window_starts(
            width, parameters.window_pixels, parameters.stride_pixels
        ):
            column_end = min(column + parameters.window_pixels, width)
            window = np.s_[row:row_end, column:column_end]
            samples = change[window][source_valid[window]]
            threshold, reason, qc = _otsu_threshold(samples, parameters)
            window_receipts.append(
                {
                    "row": row,
                    "column": column,
                    "height": row_end - row,
                    "width": column_end - column,
                    "valid_samples": int(samples.size),
                    "threshold_db": threshold,
                    "status": (
                        "qualified_candidate_window"
                        if threshold is not None
                        else "abstained"
                    ),
                    "reason": reason,
                    "qc": qc,
                }
            )
            if threshold is not None:
                window_sum = threshold_sum[window]
                window_count = threshold_count[window]
                window_sum[source_valid[window]] += threshold
                window_count[source_valid[window]] += 1

    classified = source_valid & (threshold_count > 0)
    candidate = np.full((height, width), 255, dtype="uint8")
    if classified.any():
        threshold_surface = (
            threshold_sum[classified] / threshold_count[classified]
        ).astype("float32")
        candidate[classified] = (
            (change[classified] >= threshold_surface)
            & (change[classified] > 0)
            & (vv_change[classified] > 0)
            & (vh_change[classified] > 0)
        ).astype("uint8")

    config = asdict(parameters)
    config.pop("max_terrain_slope_degrees")  # No terrain layer in this adapter.
    reason_counts = dict(
        sorted(Counter(row["reason"] for row in window_receipts if row["reason"]).items())
    )
    summary: dict[str, Any] = {
        "method": "overlapping_window_otsu_s1grd_sigma0_db_darkening_v1",
        "source_radiometry": "linear_sigma0_VV_VH_pre_and_post",
        "configuration": config,
        "total_cells": int(candidate.size),
        "source_valid_cells": int(source_valid.sum()),
        "source_invalid_cells": int((~source_valid).sum()),
        "histogram_abstained_cells": int((source_valid & ~classified).sum()),
        "classified_cells": int(classified.sum()),
        "classified_non_candidate_cells": int((candidate == 0).sum()),
        "candidate_cells": int((candidate == 1).sum()),
        "qualified_windows": sum(
            row["threshold_db"] is not None for row in window_receipts
        ),
        "total_windows": len(window_receipts),
        "reason_counts": reason_counts,
        "window_receipts": window_receipts,
        "result_status": (
            "candidate_classification_available"
            if classified.any()
            else "abstained_no_classified_cells"
        ),
    }
    return candidate, summary
