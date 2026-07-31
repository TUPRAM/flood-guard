from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from floodguard.label_factory.adjudication import (
    AdjudicationError,
    AdjudicationOutcome,
    append_adjudication_record,
    build_adjudication_queue,
    build_adjudication_record,
    load_adjudication_log,
    pair_locked_annotations,
    unresolved_queue_items,
)
from floodguard.label_factory.annotations import AnnotationRecord, LabelClass


def test_pairing_uses_latest_locked_revision_for_explicit_reviewers() -> None:
    a1 = _annotation("ANN-A1", "RV-A", revision=1)
    a2 = replace(
        a1,
        annotation_id="ANN-A2",
        reviewer_revision=2,
        primary_class=LabelClass.DRY_LAND,
        created_at_utc=a1.created_at_utc + timedelta(hours=1),
        locked_at_utc=a1.locked_at_utc + timedelta(hours=1),  # type: ignore[operator]
    )
    b = _annotation("ANN-B1", "RV-B")

    pairs = pair_locked_annotations(
        [a1, b, a2], reviewer_a_id="RV-A", reviewer_b_id="RV-B"
    )

    assert len(pairs) == 1
    assert pairs[0].reviewer_a.annotation_id == "ANN-A2"
    assert pairs[0].reviewer_b.annotation_id == "ANN-B1"


def test_pairing_rejects_missing_or_same_reviewer() -> None:
    a = _annotation("ANN-A", "RV-A")
    with pytest.raises(AdjudicationError, match="must differ"):
        pair_locked_annotations([a], reviewer_a_id="RV-A", reviewer_b_id="RV-A")
    with pytest.raises(AdjudicationError, match="lacks a locked review"):
        pair_locked_annotations([a], reviewer_a_id="RV-A", reviewer_b_id="RV-B")


def test_queue_contains_only_explicit_disagreement_or_ambiguity_reasons() -> None:
    a = _annotation("ANN-A", "RV-A", geometry="POLYGON ((0 0, 1 0, 1 1, 0 0))")
    b_same = _annotation("ANN-B", "RV-B", geometry=" polygon ((0 0, 1 0, 1 1, 0 0)) ")
    pair_same = pair_locked_annotations(
        [a, b_same], reviewer_a_id="RV-A", reviewer_b_id="RV-B"
    )[0]
    assert build_adjudication_queue(
        [pair_same], created_at_utc=_now()
    ) == ()

    b_changed = replace(
        b_same,
        primary_class=LabelClass.UNCERTAIN_WATER_CHANGE,
        confidence="low",
        ambiguity_reason_codes=("temporal_mismatch",),
    )
    pair_changed = pair_locked_annotations(
        [a, b_changed], reviewer_a_id="RV-A", reviewer_b_id="RV-B"
    )[0]
    queue = build_adjudication_queue([pair_changed], created_at_utc=_now())

    assert len(queue) == 1
    assert set(queue[0].reason_codes) == {
        "class_disagreement",
        "low_confidence_b",
        "uncertain_b",
    }
    assert queue[0].reviewer_a_annotation_id == "ANN-A"
    assert len(queue[0].reviewer_a_sha256) == 64


def test_adjudication_outcomes_derive_only_protocol_allowed_values() -> None:
    a = _annotation("ANN-A", "RV-A", primary_class=LabelClass.DRY_LAND)
    b = _annotation("ANN-B", "RV-B", primary_class=LabelClass.TEMPORARY_FLOOD)
    pair = pair_locked_annotations(
        [a, b], reviewer_a_id="RV-A", reviewer_b_id="RV-B"
    )[0]
    queue = build_adjudication_queue([pair], created_at_utc=_now())[0]

    accepted = build_adjudication_record(
        queue,
        pair,
        adjudication_id="ADJ-1",
        adjudicator_id="RV-C",
        outcome="accept_b",
        ambiguity_reason_codes=("class_disagreement",),
        resolved_at_utc=_now(),
        locked_at_utc=_now(),
        protocol_version="protocol_v1",
    )
    assert accepted.final_primary_class is LabelClass.TEMPORARY_FLOOD
    assert accepted.reviewer_b_sha256 == queue.reviewer_b_sha256

    uncertain = build_adjudication_record(
        queue,
        pair,
        adjudication_id="ADJ-2",
        adjudicator_id="RV-C",
        outcome=AdjudicationOutcome.UNCERTAIN,
        ambiguity_reason_codes=("temporal_mismatch",),
        resolved_at_utc=_now(),
        locked_at_utc=_now(),
        protocol_version="protocol_v1",
    )
    assert uncertain.final_primary_class is LabelClass.UNCERTAIN_WATER_CHANGE

    with pytest.raises(AdjudicationError, match="redraw.*final_geometry"):
        build_adjudication_record(
            queue,
            pair,
            adjudication_id="ADJ-3",
            adjudicator_id="RV-C",
            outcome="redraw",
            final_primary_class=1,
            ambiguity_reason_codes=("geometry_disagreement",),
            resolved_at_utc=_now(),
            locked_at_utc=_now(),
            protocol_version="protocol_v1",
        )


def test_immutable_adjudication_log_is_hash_chained_and_single_resolution(
    tmp_path: Path,
) -> None:
    pair, queue = _disagreement_pair_and_queue()
    record = build_adjudication_record(
        queue,
        pair,
        adjudication_id="ADJ-1",
        adjudicator_id="RV-C",
        outcome="accept_a",
        ambiguity_reason_codes=("class_disagreement",),
        resolved_at_utc=_now(),
        locked_at_utc=_now(),
        protocol_version="protocol_v1",
    )
    path = tmp_path / "adjudications.jsonl"
    append_adjudication_record(path, record)
    assert load_adjudication_log(path) == [record]
    assert unresolved_queue_items([queue], [record]) == ()
    with pytest.raises(FrozenInstanceError):
        record.notes = "changed"  # type: ignore[misc]
    with pytest.raises(AdjudicationError, match="already exists|already resolved"):
        append_adjudication_record(path, record)

    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["record"]["adjudicator_id"] = "tampered"
    path.write_text(json.dumps(envelope) + "\n", encoding="utf-8")
    with pytest.raises(AdjudicationError, match="hash mismatch"):
        load_adjudication_log(path)


def test_unresolved_queue_rejects_unknown_resolution() -> None:
    pair, queue = _disagreement_pair_and_queue()
    record = build_adjudication_record(
        queue,
        pair,
        adjudication_id="ADJ-1",
        adjudicator_id="RV-C",
        outcome="accept_a",
        ambiguity_reason_codes=("class_disagreement",),
        resolved_at_utc=_now(),
        locked_at_utc=_now(),
        protocol_version="protocol_v1",
    )
    unknown = replace(record, queue_id="ADJQ-unknown")
    with pytest.raises(AdjudicationError, match="unknown queue ids"):
        unresolved_queue_items([queue], [unknown])


def _disagreement_pair_and_queue():
    a = _annotation("ANN-A", "RV-A", primary_class=LabelClass.DRY_LAND)
    b = _annotation("ANN-B", "RV-B", primary_class=LabelClass.TEMPORARY_FLOOD)
    pair = pair_locked_annotations(
        [a, b], reviewer_a_id="RV-A", reviewer_b_id="RV-B"
    )[0]
    return pair, build_adjudication_queue([pair], created_at_utc=_now())[0]


def _annotation(
    annotation_id: str,
    reviewer_id: str,
    *,
    revision: int = 1,
    **overrides: object,
) -> AnnotationRecord:
    started = datetime(2024, 9, 16, 1, 0, tzinfo=timezone.utc)
    values: dict[str, object] = {
        "annotation_id": annotation_id,
        "event_id": "TH-MAESAI-2024-09",
        "tile_id": "TILE-1",
        "query_region_id": "QUERY-1",
        "reviewer_id": reviewer_id,
        "reviewer_revision": revision,
        "primary_class": LabelClass.TEMPORARY_FLOOD,
        "confidence": "high",
        "ambiguity_reason_codes": (),
        "evidence_layers_used": ("pre_vv", "post_vv", "dem"),
        "review_complete": True,
        "reviewed_extent": "POLYGON ((0 0, 2 0, 2 2, 0 0))",
        "geometry": "POLYGON ((0 0, 1 0, 1 1, 0 0))",
        "review_started_at": started,
        "review_finished_at": started + timedelta(minutes=10),
        "protocol_version": "protocol_v1",
        "tool_version": "qgis_v1",
        "model_predictions_visible": False,
        "other_reviewer_annotations_visible": False,
        "created_at_utc": started + timedelta(minutes=11),
        "locked_at_utc": started + timedelta(minutes=12),
    }
    values.update(overrides)
    return AnnotationRecord(**values)  # type: ignore[arg-type]


def _now() -> datetime:
    return datetime(2024, 9, 17, 1, 0, tzinfo=timezone.utc)
