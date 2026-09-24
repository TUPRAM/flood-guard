"""Contract tests for the separate GEOID radar benchmark runner."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "benchmark_geoid_flood_sar.py"
SPEC = importlib.util.spec_from_file_location("benchmark_geoid_flood_sar", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


def test_score_excludes_invalid_and_reports_abstained_flood() -> None:
    candidate = np.array([[1, 0, 255, 1, 0, 1]], dtype="uint8")
    label = np.array([[2, 0, 2, 1, 255, 2]], dtype="uint8")
    validity = np.array([[1, 1, 1, 1, 1, 0]], dtype="uint8")
    primary = benchmark.score_candidate(
        candidate, label, validity, include_permanent_as_negative=True
    )
    secondary = benchmark.score_candidate(
        candidate, label, validity, include_permanent_as_negative=False
    )
    assert primary["evaluable_cells"] == 4
    assert primary["covered_cells"] == 3
    assert primary["reference_flood_cells"] == 2
    assert primary["covered_reference_flood_cells"] == 1
    assert primary["true_positive"] == 1
    assert primary["false_positive"] == 1
    assert primary["false_negative"] == 0
    assert primary["true_negative"] == 1
    assert primary["evaluated_coverage"] == 0.75
    assert primary["dice"] == pytest.approx(2 / 3)
    assert secondary["evaluable_cells"] == 3
    assert secondary["false_positive"] == 0
    assert secondary["dice"] == 1


def test_metrics_are_pooled_and_zero_denominators_are_null() -> None:
    empty = {
        "true_positive": 0, "false_positive": 0,
        "false_negative": 0, "true_negative": 0,
        "evaluable_cells": 0, "covered_cells": 0,
        "reference_flood_cells": 0, "covered_reference_flood_cells": 0,
        "predicted_flood_cells": 0,
    }
    metrics = benchmark.metrics_from_counts(empty)
    assert metrics["dice"] is None
    assert metrics["evaluated_coverage"] is None
    assert metrics["true_positive"] == 0


def test_protocol_must_match_pre_scoring_commit(tmp_path: Path) -> None:
    source = ROOT / benchmark.PROTOCOL_RELATIVE
    protocol, source_hash = benchmark.load_protocol(source)
    assert protocol["dataset"]["aoi_id"] == "EMSR712-3"
    assert source_hash == benchmark.file_sha256(source)
    altered = tmp_path / "protocol.json"
    content = json.loads(source.read_text(encoding="utf-8"))
    content["purpose"] = "changed after the frozen commit"
    altered.write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(benchmark.BenchmarkError, match="pre-scoring commit"):
        benchmark.load_protocol(altered)


def test_discovery_requires_all_published_files_and_hashes(tmp_path: Path) -> None:
    root = tmp_path / "source"
    lines = []
    for number in range(29):
        tile = f"EMSR712-3-{number}"
        roles = {
            "s1grd": (
                f"{tile}_s1grd_pre_20230908T170931.tif",
                f"{tile}_s1grd_post_20240103T053406.tif",
            ),
            "label": (f"{tile}_label.tif",),
            "validity": (f"{tile}_validity.tif",),
        }
        for folder, filenames in roles.items():
            for filename in filenames:
                relative = f"sample/geoid-flood/EMSR712-3/{folder}/{filename}"
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(relative.encode())
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                lines.append(f"{digest}  {relative}")
    sums = tmp_path / "SHA256SUMS"
    sums.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tiles, inventory = benchmark.discover_tiles(root, sums)
    assert len(tiles) == 29
    assert len(inventory) == 116
    bad_path = root / lines[0].split("  ", 1)[1]
    bad_path.write_bytes(b"tampered")
    with pytest.raises(benchmark.BenchmarkError, match="SHA-256 mismatch"):
        benchmark.discover_tiles(root, sums)


def test_grid_mismatch_refused() -> None:
    normal = {
        "driver": "GTiff", "height": 1024, "width": 1024,
        "count": 2, "dtype": "float32", "crs": "EPSG:32632",
        "transform": from_origin(471040, 5898240, 10, 10),
    }
    with (
        MemoryFile() as pre_memory,
        MemoryFile() as post_memory,
        pre_memory.open(**normal) as pre,
        post_memory.open(
            **{**normal, "transform": from_origin(471050, 5898240, 10, 10)}
        ) as post,
        pytest.raises(benchmark.BenchmarkError, match="grids differ"),
    ):
        benchmark._validate_grid(pre, [post])


def test_receipt_and_raster_tampering_refused(tmp_path: Path) -> None:
    directory = tmp_path / "result"
    (directory / "candidates").mkdir(parents=True)
    outputs = {}
    for number in range(29):
        relative = f"candidates/EMSR712-3-{number}_candidate.tif"
        path = directory / relative
        path.write_bytes(f"candidate {number}".encode())
        outputs[relative] = benchmark.file_sha256(path)
    receipt = {"candidate_outputs": outputs, "dice": 0.2}
    receipt["receipt_sha256"] = benchmark.canonical_sha256(receipt)
    path = directory / "result.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    assert benchmark.verify_result_receipt(path)["dice"] == 0.2
    receipt["dice"] = 1
    path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(benchmark.BenchmarkError, match="self-hash"):
        benchmark.verify_result_receipt(path)
    receipt["dice"] = 0.2
    path.write_text(json.dumps(receipt), encoding="utf-8")
    (directory / next(iter(outputs))).write_bytes(b"tampered")
    with pytest.raises(benchmark.BenchmarkError, match="differs"):
        benchmark.verify_result_receipt(path)
