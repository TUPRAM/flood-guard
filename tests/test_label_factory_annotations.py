from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from floodguard.label_factory.annotations import (
    AnnotationRecord,
    AnnotationValidationError,
    LabelClass,
    append_annotation_record,
    derive_binary_target,
    derive_binary_targets,
    load_annotation_log,
)
from floodguard.label_factory.contracts import FloodLabel


def test_annotation_taxonomy_uses_canonical_contract_enum() -> None:
    assert LabelClass is FloodLabel
    assert LabelClass.UNREVIEWED == 255


def test_binary_derivation_excludes_unknown_states_instead_of_making_them_dry() -> None:
    labels = [0, 1, 2, 3, 4, 255]

    result = derive_binary_targets(labels)

    assert result.targets == (0, 1, 0, None, None, None)
    assert result.eligible_indices == (0, 1, 2)
    assert result.excluded_indices == (3, 4, 5)
    assert result.eligible_targets == (0, 1, 0)
    assert derive_binary_target(LabelClass.UNCERTAIN_WATER_CHANGE) is None


def test_annotation_requires_identity_extent_and_blinding() -> None:
    with pytest.raises(AnnotationValidationError, match="reviewer_id"):
        _record(reviewer_id=" ")
    with pytest.raises(AnnotationValidationError, match="reviewed_extent"):
        _record(reviewed_extent="")
    with pytest.raises(AnnotationValidationError, match="model predictions"):
        _record(model_predictions_visible=True)
    with pytest.raises(AnnotationValidationError, match="other reviewer"):
        _record(other_reviewer_annotations_visible=True)


def test_uncertain_annotation_requires_reason_and_cannot_train() -> None:
    with pytest.raises(AnnotationValidationError, match="ambiguity reason"):
        _record(
            primary_class=LabelClass.UNCERTAIN_WATER_CHANGE,
            ambiguity_reason_codes=(),
        )

    uncertain = _record(
        primary_class=LabelClass.UNCERTAIN_WATER_CHANGE,
        ambiguity_reason_codes=("temporal_mismatch",),
    )

    assert uncertain.is_binary_training_eligible is False


def test_frozen_record_and_append_only_hash_chain(tmp_path: Path) -> None:
    path = tmp_path / "annotations.jsonl"
    first = _record()

    first_hash = append_annotation_record(path, first)
    second = replace(
        first,
        annotation_id="ANN-2",
        reviewer_revision=2,
        created_at_utc=first.created_at_utc + timedelta(minutes=2),
        locked_at_utc=first.locked_at_utc + timedelta(minutes=2),  # type: ignore[operator]
    )
    second_hash = append_annotation_record(path, second)

    loaded = load_annotation_log(path)
    assert [record.annotation_id for record in loaded] == ["ANN-1", "ANN-2"]
    assert first_hash != second_hash
    with pytest.raises(FrozenInstanceError):
        first.reviewer_id = "changed"  # type: ignore[misc]
    with pytest.raises(AnnotationValidationError, match="already exists"):
        append_annotation_record(path, first)
    with pytest.raises(AnnotationValidationError, match="expected 3"):
        append_annotation_record(
            path,
            replace(
                second,
                annotation_id="ANN-3",
                reviewer_revision=4,
                created_at_utc=second.created_at_utc + timedelta(minutes=2),
                locked_at_utc=second.locked_at_utc + timedelta(minutes=2),  # type: ignore[operator]
            ),
        )


def test_annotation_log_detects_content_tampering(tmp_path: Path) -> None:
    path = tmp_path / "annotations.jsonl"
    append_annotation_record(path, _record())
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["record"]["reviewer_id"] = "tampered"
    path.write_text(json.dumps(envelope) + "\n", encoding="utf-8")

    with pytest.raises(AnnotationValidationError, match="hash mismatch"):
        load_annotation_log(path)


def _record(**overrides: object) -> AnnotationRecord:
    start = datetime(2024, 9, 16, 1, 0, tzinfo=timezone.utc)
    values: dict[str, object] = {
        "annotation_id": "ANN-1",
        "event_id": "TH-MAESAI-2024-09",
        "tile_id": "TILE-1",
        "query_region_id": "REGION-1",
        "reviewer_id": "RV-A",
        "reviewer_revision": 1,
        "primary_class": LabelClass.TEMPORARY_FLOOD,
        "confidence": "high",
        "ambiguity_reason_codes": (),
        "evidence_layers_used": ("pre_vv", "post_vv", "dem"),
        "review_complete": True,
        "reviewed_extent": "POLYGON ((0 0, 1 0, 1 1, 0 1, 0 0))",
        "geometry": "POLYGON ((0 0, 1 0, 1 1, 0 1, 0 0))",
        "review_started_at": start,
        "review_finished_at": start + timedelta(minutes=10),
        "protocol_version": "annotation_v1",
        "tool_version": "qgis_template_v1",
        "model_predictions_visible": False,
        "other_reviewer_annotations_visible": False,
        "created_at_utc": start + timedelta(minutes=11),
        "locked_at_utc": start + timedelta(minutes=12),
    }
    values.update(overrides)
    return AnnotationRecord(**values)  # type: ignore[arg-type]
