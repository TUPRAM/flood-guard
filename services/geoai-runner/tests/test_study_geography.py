"""Network-free checks for the cartographic country-label projection."""

import importlib.util
from pathlib import Path

module_path = Path(__file__).parents[1] / "scripts" / "acquire_study_geography.py"
spec = importlib.util.spec_from_file_location("study_geography", module_path)
assert spec and spec.loader
geography = importlib.util.module_from_spec(spec)
spec.loader.exec_module(geography)


def test_country_inference_respects_holes_and_disconnected_islands():
    mainland = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
    lake = [[3, 3], [7, 3], [7, 7], [3, 7], [3, 3]]
    island = [[20, 20], [21, 20], [21, 21], [20, 21], [20, 20]]
    polygons = [[mainland, lake], [island]]
    assert geography.contains([1, 1], polygons)
    assert not geography.contains([5, 5], polygons)
    assert geography.contains([20.5, 20.5], polygons)
    assert not geography.contains([-1, -1], polygons)
