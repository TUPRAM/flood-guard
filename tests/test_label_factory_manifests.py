from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

from floodguard.label_factory.event_registry import EventRecord, SourceAssetRecord
from floodguard.label_factory.manifests import (
    ManifestContractError,
    build_grid_manifests,
    validate_grid_manifests,
)
from label_factory_processing_fixtures import synthetic_processing_receipt
from label_factory_processing_fixtures import synthetic_processing_evidence
from floodguard.label_factory.processing_alignment import (
    build_processing_alignment_receipt,
)
from test_label_factory_event_registry import event_row, valid_sources


def source_records() -> list[SourceAssetRecord]:
    return [SourceAssetRecord.from_mapping(row) for row in valid_sources()]


def processing_receipt(tmp_path: Path, event: EventRecord) -> dict[str, object]:
    sources = source_records()
    return synthetic_processing_receipt(tmp_path, [event], sources)


def assignment_row(
    *,
    x_index: int = 0,
    y_index: int = 0,
    role: str = "training_and_query_pool",
    overlap_group: str = "TH-MAESAI-G000",
) -> dict[str, object]:
    return {
        "event_id": "TH-MAESAI-2024-09",
        "x_index": x_index,
        "y_index": y_index,
        "dataset_role": role,
        "overlap_group_id": overlap_group,
        "valid_data_fraction": 0.95,
        "feature_schema_version": "sar_change_v2",
        "source_timestamp": "2024-09-21T00:00:00Z",
        "confidence_class": "medium",
        "assumptions": "Synthetic grid contract only; no real flood evidence.",
    }


def test_builds_deterministic_complete_tiles_and_query_cores(tmp_path: Path) -> None:
    event = EventRecord.from_mapping(event_row())
    assignments = [
        assignment_row(x_index=1, overlap_group="G-B"),
        assignment_row(x_index=0, overlap_group="G-A"),
    ]

    receipt = processing_receipt(tmp_path, event)
    manifests = build_grid_manifests(
        [event],
        assignments,
        source_records(),
        receipt,
        allow_ungoverned_fixture=True,
    )

    assert len(manifests.tiles) == 2
    assert len(manifests.query_regions) == 32
    first_tile = manifests.tiles.iloc[0]
    first_query = manifests.query_regions.iloc[0]
    assert first_tile["tile_id"].endswith("_X00000_Y00000")
    assert first_tile["bbox_min_x"] == 320000
    assert first_query["query_region_id"].endswith("_R00_C00_S64")
    assert first_query["bbox_max_y"] == 2202560
    assert first_query["source_registry_sha256"]
    assert first_query["processing_alignment_receipt_sha256"] == receipt["receipt_sha256"]
    assert first_query["pre_product_ids"] == "PRODUCT-S1-PRE-FIXTURE"
    assert first_query["event_product_ids"] == "PRODUCT-S1-EVENT-FIXTURE"
    assert bool(first_query["eligible_for_review_queue"]) is True
    assert bool(first_query["eligible_for_human_annotation"]) is True
    assert bool(first_query["eligible_for_active_selection"]) is True
    assert bool(first_query["eligible_for_query_model_training"]) is False
    assert bool(first_query["query_model_only"]) is True
    assert bool(first_query["eligible_for_decision_layer"]) is False
    assert bool(first_query["eligible_for_fpps"]) is False
    assert bool(first_query["eligible_for_warning"]) is False


def test_fixed_and_geographic_roles_are_not_active_learning_eligible(
    tmp_path: Path,
) -> None:
    test_event_row = event_row(role="untouched_geographic_test")
    event = EventRecord.from_mapping(test_event_row)
    assignment = assignment_row(role="untouched_geographic_test")

    queries = build_grid_manifests(
        [event],
        [assignment],
        source_records(),
        processing_receipt(tmp_path, event),
        allow_ungoverned_fixture=True,
    ).query_regions

    assert queries["eligible_for_review_queue"].eq(False).all()
    assert queries["eligible_for_query_model_training"].eq(False).all()
    assert queries["selected"].eq(False).all()
    assert set(queries["eligible_for_training_after_human_review"]) == {"no"}


def test_role_escalation_and_cross_role_overlap_groups_fail_closed(
    tmp_path: Path,
) -> None:
    fixed_event = EventRecord.from_mapping(
        event_row(role="fixed_within_event_development")
    )
    with pytest.raises(ManifestContractError, match="cannot be escalated"):
        build_grid_manifests(
            [fixed_event],
            [assignment_row()],
            source_records(),
            processing_receipt(tmp_path / "fixed", fixed_event),
            allow_ungoverned_fixture=True,
        )

    training_event = EventRecord.from_mapping(event_row())
    cross_role = [
        assignment_row(role="training_and_query_pool", overlap_group="SHARED"),
        assignment_row(
            x_index=1,
            role="reviewer_calibration",
            overlap_group="SHARED",
        ),
    ]
    with pytest.raises(ManifestContractError, match="crosses dataset roles"):
        build_grid_manifests(
            [training_event],
            cross_role,
            source_records(),
            processing_receipt(tmp_path / "training", training_event),
            allow_ungoverned_fixture=True,
        )


def test_geographic_test_role_is_event_wide_not_a_tile_level_escape_hatch(
    tmp_path: Path,
) -> None:
    training_event = EventRecord.from_mapping(event_row())
    with pytest.raises(ManifestContractError, match="requires an event"):
        build_grid_manifests(
            [training_event],
            [assignment_row(role="untouched_geographic_test")],
            source_records(),
            processing_receipt(tmp_path / "training", training_event),
            allow_ungoverned_fixture=True,
        )

    test_event = EventRecord.from_mapping(
        event_row(role="untouched_geographic_test")
    )
    with pytest.raises(ManifestContractError, match="cannot contain"):
        build_grid_manifests(
            [test_event],
            [assignment_row()],
            source_records(),
            processing_receipt(tmp_path / "test", test_event),
            allow_ungoverned_fixture=True,
        )


def test_grid_builder_rejects_duplicate_cores_and_legacy_feature_schema(
    tmp_path: Path,
) -> None:
    event = EventRecord.from_mapping(event_row())
    receipt = processing_receipt(tmp_path, event)
    duplicate = [assignment_row(), assignment_row()]
    with pytest.raises(ManifestContractError, match="Duplicate core identifier"):
        build_grid_manifests(
            [event],
            duplicate,
            source_records(),
            receipt,
            allow_ungoverned_fixture=True,
        )

    legacy = assignment_row()
    legacy["feature_schema_version"] = "legacy_real_weak_sar_v1"
    with pytest.raises(ManifestContractError, match="reproduction-only"):
        build_grid_manifests(
            [event],
            [legacy],
            source_records(),
            receipt,
            allow_ungoverned_fixture=True,
        )


@pytest.mark.parametrize(
    ("target", "column", "value", "message"),
    [
        ("tiles", "bbox_min_x", 1, "non-canonical bbox_min_x"),
        ("queries", "eligible_for_fpps", True, "eligible_for_fpps"),
        ("queries", "source_registry_sha256", "f" * 64, "source_registry_sha256"),
        (
            "queries",
            "processing_alignment_receipt_sha256",
            "f" * 64,
            "processing_alignment_receipt_sha256",
        ),
        ("queries", "query_region_id", "ALTERED", "key set differs"),
    ],
)
def test_validator_rebuilds_canonical_rows_and_detects_tampering(
    tmp_path: Path, target: str, column: str, value: object, message: str
) -> None:
    event = EventRecord.from_mapping(event_row())
    receipt = processing_receipt(tmp_path, event)
    canonical = build_grid_manifests(
        [event],
        [assignment_row()],
        source_records(),
        receipt,
        allow_ungoverned_fixture=True,
    )
    tiles = canonical.tiles.copy()
    queries = canonical.query_regions.copy()
    frame = tiles if target == "tiles" else queries
    frame.loc[frame.index[0], column] = value

    with pytest.raises(ManifestContractError, match=message):
        validate_grid_manifests(
            [event],
            source_records(),
            tiles,
            queries,
            receipt,
            allow_ungoverned_fixture=True,
        )


def test_validator_detects_incomplete_query_lattice(tmp_path: Path) -> None:
    event = EventRecord.from_mapping(event_row())
    receipt = processing_receipt(tmp_path, event)
    canonical = build_grid_manifests(
        [event],
        [assignment_row()],
        source_records(),
        receipt,
        allow_ungoverned_fixture=True,
    )

    with pytest.raises(ManifestContractError, match="key set differs"):
        validate_grid_manifests(
            [event],
            source_records(),
            canonical.tiles,
            canonical.query_regions.iloc[:-1],
            receipt,
            allow_ungoverned_fixture=True,
        )


def test_grid_builder_requires_processed_coverage_of_every_tile(tmp_path: Path) -> None:
    event = EventRecord.from_mapping(event_row())
    sources = source_records()
    evidence = synthetic_processing_evidence(
        tmp_path / "processing",
        [event],
        sources,
    )
    evidence["width_pixels"] = 128
    evidence["height_pixels"] = 128
    evidence["affine_f"] = event.grid_origin_y + 128 * event.analysis_resolution_m
    receipt = build_processing_alignment_receipt(
        [event], sources, evidence, allow_ungoverned_fixture=True
    )

    with pytest.raises(ManifestContractError, match="does not cover"):
        build_grid_manifests(
            [event],
            [assignment_row()],
            sources,
            receipt,
            allow_ungoverned_fixture=True,
        )


def test_cli_help_and_operational_failure_contract() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    for script_name in (
        "build_label_factory_grid.py",
        "validate_label_factory_manifests.py",
    ):
        script = repo_root / "scripts" / script_name
        help_result = subprocess.run(
            [sys.executable, str(script), "--help"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        assert help_result.returncode == 0
        assert "usage:" in help_result.stdout.lower()
        assert "governance-package" in help_result.stdout

    blocked = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "build_label_factory_grid.py"),
            "--events",
            "missing.csv",
            "--source-assets",
            "missing.csv",
            "--governance-package",
            "missing_governance",
            "--processing-alignment-receipt",
            "missing.json",
            "--tile-assignments",
            "missing.csv",
            "--tile-output",
            "tiles.csv",
            "--query-output",
            "queries.csv",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert blocked.returncode == 2
    assert "BLOCKED:" in blocked.stderr
