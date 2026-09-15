"""Network-free contracts for scientific preview values and frozen evidence roles."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

SCRIPT = Path(__file__).parents[1] / "scripts/export_study_visuals.py"
SPEC = importlib.util.spec_from_file_location("export_study_visuals", SCRIPT)
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)


@pytest.fixture
def preview_dependencies():
    """Rendering uses the existing optional realpipeline visualization dependencies."""
    pytest.importorskip("matplotlib")
    pytest.importorskip("PIL")


def test_error_map_retains_false_positives_false_negatives_and_invalid_pixels():
    probability = np.array([[0.1, 0.9, 0.9], [0.1, 0.5, np.nan]])
    reference = np.array([[0, 1, 0], [1, 1, -1]])
    binary, error = exporter.binary_error(probability, reference)
    np.testing.assert_array_equal(error[:, :2], [[0, 1], [3, 1]])
    assert error[0, 2] == 2
    assert binary[1, 1] == 1  # Frozen threshold includes exactly 0.5.
    assert np.isnan(binary[1, 2]) and np.isnan(error[1, 2])


def test_invalid_probability_on_reference_support_is_refused():
    with pytest.raises(ValueError, match="support differ"):
        exporter.binary_error(np.array([[np.nan]]), np.array([[1]]))


def test_preview_has_exact_category_colors_and_embedded_provenance(tmp_path, preview_dependencies):
    from PIL import Image

    metadata = exporter.envelope("fixture 2024", "CC0-1.0", dataset="synthetic fixture")
    values = np.array([[0, 1, 2], [3, np.nan, 0]])
    path = tmp_path / "study/error.png"
    layer = exporter.render_preview(values, "error", path, metadata, tmp_path)
    assert layer["url"] == "/study/error.png"
    assert layer["native_width"] == 3 and layer["native_height"] == 2
    assert exporter.verify(tmp_path, layer) == path
    with Image.open(path) as image:
        pixels = np.asarray(image)
        assert pixels[0, 2].tolist() == [219, 122, 40]  # False positive.
        assert pixels[1, 0].tolist() == [175, 62, 129]  # False negative.
        assert pixels[1, 1].tolist() == [185, 185, 185]  # Invalid remains explicit.
        for key in ("data_mode", "source_timestamp", "license", "assumptions"):
            assert json.loads(image.info[key]) == metadata[key]
        assert json.loads(image.info["can_feed_decision_layer"]) is False


def test_display_downsampling_is_nearest_only_and_does_not_create_mixed_classes(
    tmp_path, preview_dependencies
):
    from PIL import Image

    values = np.tile([[0, 1], [1, 0]], (4, 4))
    layer = exporter.render_preview(
        values,
        "reference",
        tmp_path / "reference.png",
        exporter.envelope("fixture", "CC0", dataset="fixture"),
        tmp_path,
        limit=3,
    )
    assert (layer["width"], layer["height"]) == (3, 3)
    assert layer["display"]["resampling"] == "nearest_neighbour_display_only"
    with Image.open(tmp_path / "reference.png") as image:
        colors = set(map(tuple, np.asarray(image).reshape(-1, 3)))
    assert colors <= {(242, 241, 233), (33, 127, 163)}


def test_preview_resume_rejects_modified_png(tmp_path, preview_dependencies):
    layer = exporter.render_preview(
        np.zeros((2, 2)),
        "probability",
        tmp_path / "p.png",
        exporter.envelope("fixture", "CC0", dataset="fixture"),
        tmp_path,
    )
    entry = {"status": "available", "layers": {"probability": layer}}
    assert exporter.reusable(entry, tmp_path, ("probability",))
    (tmp_path / "p.png").write_bytes(b"modified")
    with pytest.raises(ValueError, match="Source receipt changed"):
        exporter.reusable(entry, tmp_path, ("probability",))


def test_missing_context_stays_unavailable_and_preserves_recorded_zero_support():
    row = {
        "raw": {"full_valid": {"blocked_reason": "empty_evaluation_region"}},
        "calibrated": {
            "n_valid_pixels": 0,
            "full_valid": {"n_reference_positive": 0, "blocked_reason": "empty_evaluation_region"},
        },
        "combined_screening": {"n_accepted_pixels": 0},
        "status": "no_valid_pixels",
    }
    report = {"dataset": "fixture", "calibration": {}, "abstention": {}}
    metadata = {"source_timestamp": "fixture", "checkpoint": {"sha256": "a" * 64}}
    entry = exporter.model_entry(report, row, metadata, {})
    assert entry["status"] == "unavailable"
    assert entry["reason"] == "no_valid_context_support"
    assert entry["layers"] == {}
    assert entry["support"] == {
        "n_valid_pixels": 0,
        "n_accepted_pixels": 0,
        "n_reference_positive": 0,
    }
    assert "iou" not in entry["benchmark"]["calibrated"]["full_valid"]


def test_projected_extent_preserves_original_grid():
    grid = {"width": 512, "height": 512, "transform": [10, 0, 100, 0, -10, 200]}
    assert exporter.extent(grid) == [100, -4920, 5220, 200]
