from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from floodguard.label_factory.versioning import (
    ChangeKind,
    LabelsetVersionError,
    SemanticVersion,
    build_labelset_manifest,
    freeze_labelset_manifest,
    load_labelset_manifest,
    verify_labelset_content,
    verify_manifest_lineage,
)


def test_semantic_versions_have_exact_successors() -> None:
    version = SemanticVersion.parse("v0.1.0")

    assert str(version) == "0.1.0"
    assert version.next_for(ChangeKind.PATCH) == SemanticVersion(0, 1, 1)
    assert version.next_for(ChangeKind.MINOR) == SemanticVersion(0, 2, 0)
    assert version.next_for(ChangeKind.MAJOR) == SemanticVersion(1, 0, 0)


def test_manifest_binds_content_and_verifies_external_inputs() -> None:
    manifest = _initial_manifest()

    verify_labelset_content(
        manifest,
        label_content={"REGION-1": [0, 1, 255]},
        metadata={"qa": "passed", "revision": 1},
        semantics={"taxonomy": "flood_label_v1", "grid": "utm_10m_v1"},
    )
    with pytest.raises(LabelsetVersionError, match="label content"):
        verify_labelset_content(
            manifest,
            label_content={"REGION-1": [0, 0, 255]},
            metadata={"qa": "passed", "revision": 1},
            semantics={"taxonomy": "flood_label_v1", "grid": "utm_10m_v1"},
        )


def test_frozen_manifest_is_exclusive_and_tamper_evident(tmp_path: Path) -> None:
    manifest = _initial_manifest()
    path = tmp_path / "mae_sai_2024_labels_v0.1.0.json"

    freeze_labelset_manifest(manifest, path)
    assert load_labelset_manifest(path) == manifest
    with pytest.raises(LabelsetVersionError, match="cannot be overwritten"):
        freeze_labelset_manifest(manifest, path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["source_annotation_ids"] = ["ANN-TAMPERED"]
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(LabelsetVersionError, match="SHA-256"):
        load_labelset_manifest(path)


def test_minor_patch_and_major_release_meanings_are_enforced() -> None:
    parent = _initial_manifest()
    minor = build_labelset_manifest(
        labelset_name="mae_sai_2024_labels", version="0.2.0", change_kind="minor",
        label_content={"REGION-1": [0, 1, 255], "REGION-2": [2, 0]},
        metadata={"qa": "passed", "revision": 2},
        semantics={"taxonomy": "flood_label_v1", "grid": "utm_10m_v1"},
        source_annotation_ids=["ANN-1", "ANN-2"], raster_sha256_by_name={"labels.tif": "b" * 64},
        created_at_utc=datetime(2024, 9, 18, tzinfo=timezone.utc), parent=parent,
    )
    major = build_labelset_manifest(
        labelset_name="mae_sai_2024_labels", version="1.0.0", change_kind="major",
        label_content={"REGION-1": [0, 1, 255]}, metadata={"qa": "passed", "revision": 2},
        semantics={"taxonomy": "flood_label_v2", "grid": "utm_10m_v1"}, source_annotation_ids=["ANN-1"],
        raster_sha256_by_name={"labels.tif": "a" * 64}, created_at_utc=datetime(2024, 9, 19, tzinfo=timezone.utc), parent=parent,
    )
    patch = build_labelset_manifest(
        labelset_name="mae_sai_2024_labels", version="0.1.1", change_kind="patch",
        label_content={"REGION-1": [0, 1, 255]}, metadata={"qa": "passed", "revision": 2},
        semantics={"taxonomy": "flood_label_v1", "grid": "utm_10m_v1"}, source_annotation_ids=["ANN-1"],
        raster_sha256_by_name={"labels.tif": "a" * 64}, created_at_utc=datetime(2024, 9, 19, tzinfo=timezone.utc), parent=parent,
    )

    verify_manifest_lineage(minor, parent)
    verify_manifest_lineage(major, parent)
    verify_manifest_lineage(patch, parent)
    with pytest.raises(LabelsetVersionError, match="patch release cannot change"):
        build_labelset_manifest(
            labelset_name="mae_sai_2024_labels", version="0.1.1", change_kind="patch",
            label_content={"REGION-1": [1, 1, 255]}, metadata={"qa": "passed", "revision": 2},
            semantics={"taxonomy": "flood_label_v1", "grid": "utm_10m_v1"}, source_annotation_ids=["ANN-1"],
            raster_sha256_by_name={"labels.tif": "a" * 64}, parent=parent,
        )


def _initial_manifest():
    return build_labelset_manifest(
        labelset_name="mae_sai_2024_labels", version="0.1.0", change_kind="initial",
        label_content={"REGION-1": [0, 1, 255]}, metadata={"qa": "passed", "revision": 1},
        semantics={"taxonomy": "flood_label_v1", "grid": "utm_10m_v1"}, source_annotation_ids=["ANN-1"],
        raster_sha256_by_name={"labels.tif": "a" * 64}, created_at_utc=datetime(2024, 9, 17, tzinfo=timezone.utc),
    )
