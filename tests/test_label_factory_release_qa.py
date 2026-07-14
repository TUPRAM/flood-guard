from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from floodguard.label_factory.annotations import (
    AnnotationRecord,
    LabelClass,
    annotation_content_sha256,
    append_annotation_record,
)
from floodguard.label_factory.release_qa import (
    RELEASE_QA_RECEIPT_SCHEMA,
    ReleaseQAError,
    qa_report_content_sha256,
    run_release_qa_from_raw_inputs,
    verify_release_qa_artifacts,
    write_release_qa_artifacts_from_raw,
)


def test_release_qa_recomputes_raw_inputs_and_writes_self_hashed_receipt(
    tmp_path: Path,
) -> None:
    paths = _raw_inputs(tmp_path, include_query_artifacts=True)
    report, _ = run_release_qa_from_raw_inputs(paths)
    base = _base_receipt(report)

    reproduced, receipt, report_path, receipt_path = (
        write_release_qa_artifacts_from_raw(
            qa_report=report,
            base_receipt=base,
            raw_input_paths=paths,
            qa_report_path=tmp_path / "release_qa.csv",
            qa_receipt_path=tmp_path / "release_qa_receipt.json",
        )
    )

    assert reproduced.ready is True
    assert receipt["receipt_sha256"] == _receipt_hash(receipt)
    assert set(receipt["raw_input_artifacts"]) == set(paths)
    assert receipt["query_models_in_scope"] is True
    assert receipt["query_records_in_scope"] is True
    assert receipt["eligible_for_decision_layer"] is False
    assert receipt["eligible_for_fpps"] is False
    assert receipt["eligible_for_warning"] is False
    assert receipt["qa_report_file_sha256"] == hashlib.sha256(
        report_path.read_bytes()
    ).hexdigest()
    assert receipt_path.is_file()
    assert (
        verify_release_qa_artifacts(
            qa_report=report,
            qa_receipt=receipt,
            qa_report_path=report_path,
            raw_input_paths=paths,
        ).ready
        is True
    )


def test_release_qa_rejects_raw_input_tamper_even_if_report_still_says_pass(
    tmp_path: Path,
) -> None:
    paths = _raw_inputs(tmp_path)
    report, _ = run_release_qa_from_raw_inputs(paths)
    _, receipt, report_path, _ = write_release_qa_artifacts_from_raw(
        qa_report=report,
        base_receipt=_base_receipt(report),
        raw_input_paths=paths,
        qa_report_path=tmp_path / "release_qa.csv",
        qa_receipt_path=tmp_path / "release_qa_receipt.json",
    )
    source_assets = pd.read_csv(paths["source_assets"])
    source_assets.loc[0, "processing_allowed"] = False
    source_assets.to_csv(paths["source_assets"], index=False, lineterminator="\n")

    with pytest.raises(ReleaseQAError, match="artifact mismatch"):
        verify_release_qa_artifacts(
            qa_report=report,
            qa_receipt=receipt,
            qa_report_path=report_path,
            raw_input_paths=paths,
        )


def test_release_qa_rejects_receipt_and_qa_csv_tamper(tmp_path: Path) -> None:
    paths = _raw_inputs(tmp_path)
    report, _ = run_release_qa_from_raw_inputs(paths)
    _, receipt, report_path, _ = write_release_qa_artifacts_from_raw(
        qa_report=report,
        base_receipt=_base_receipt(report),
        raw_input_paths=paths,
        qa_report_path=tmp_path / "release_qa.csv",
        qa_receipt_path=tmp_path / "release_qa_receipt.json",
    )

    mutated = dict(receipt)
    mutated["eligible_for_fpps"] = True
    with pytest.raises(ReleaseQAError, match="self-hash"):
        verify_release_qa_artifacts(
            qa_report=report,
            qa_receipt=mutated,
            qa_report_path=report_path,
            raw_input_paths=paths,
        )

    report_path.write_text(
        report_path.read_text(encoding="utf-8").replace("True", "False", 1),
        encoding="utf-8",
    )
    with pytest.raises(ReleaseQAError, match="report file checksum"):
        verify_release_qa_artifacts(
            qa_report=report,
            qa_receipt=receipt,
            qa_report_path=report_path,
            raw_input_paths=paths,
        )


def test_release_qa_rejects_missing_raw_role_and_legacy_hand_authored_receipt(
    tmp_path: Path,
) -> None:
    paths = _raw_inputs(tmp_path)
    report, _ = run_release_qa_from_raw_inputs(paths)
    missing = dict(paths)
    missing.pop("usage_records")
    with pytest.raises(ReleaseQAError, match="missing=.*usage_records"):
        run_release_qa_from_raw_inputs(missing)

    hand_authored = _base_receipt(report)
    fake_report = tmp_path / "hand_authored.csv"
    pd.DataFrame(report.to_rows()).to_csv(
        fake_report, index=False, lineterminator="\n"
    )
    with pytest.raises(ReleaseQAError, match="receipt_sha256"):
        verify_release_qa_artifacts(
            qa_report=report,
            qa_receipt=hand_authored,
            qa_report_path=fake_report,
            raw_input_paths=paths,
        )


def test_release_qa_query_rows_must_remain_decision_ineligible(
    tmp_path: Path,
) -> None:
    paths = _raw_inputs(tmp_path, include_query_artifacts=True)
    queries = pd.read_csv(paths["query_records"])
    queries.loc[0, "eligible_for_fpps"] = True
    queries.to_csv(paths["query_records"], index=False, lineterminator="\n")

    report, _ = run_release_qa_from_raw_inputs(paths)

    assert report.ready is False
    assert any(
        finding.check_id == "query_model_eligible_for_fpps"
        and not finding.passed
        for finding in report.findings
    )
    with pytest.raises(ReleaseQAError, match="blocking failures"):
        write_release_qa_artifacts_from_raw(
            qa_report=report,
            base_receipt=_base_receipt(report),
            raw_input_paths=paths,
            qa_report_path=tmp_path / "release_qa.csv",
            qa_receipt_path=tmp_path / "release_qa_receipt.json",
        )


def test_release_qa_outputs_are_write_once(tmp_path: Path) -> None:
    paths = _raw_inputs(tmp_path)
    report, _ = run_release_qa_from_raw_inputs(paths)
    kwargs = {
        "qa_report": report,
        "base_receipt": _base_receipt(report),
        "raw_input_paths": paths,
        "qa_report_path": tmp_path / "release_qa.csv",
        "qa_receipt_path": tmp_path / "release_qa_receipt.json",
    }
    write_release_qa_artifacts_from_raw(**kwargs)

    with pytest.raises(ReleaseQAError, match="cannot be overwritten"):
        write_release_qa_artifacts_from_raw(**kwargs)


def test_release_qa_accepts_multiple_audited_usages_for_one_training_region(
    tmp_path: Path,
) -> None:
    paths = _raw_inputs(tmp_path)
    usage = pd.read_csv(paths["usage_records"])
    usage = pd.concat(
        [
            usage,
            pd.DataFrame(
                [{"region_id": "TRAIN-1", "purpose": "acquisition"}]
            ),
        ],
        ignore_index=True,
    )
    usage.to_csv(paths["usage_records"], index=False, lineterminator="\n")

    report, _ = run_release_qa_from_raw_inputs(paths)

    assert report.ready is True
    usage_entities = {
        finding.entity_id
        for finding in report.findings
        if finding.check_id == "usage_has_dataset_role"
    }
    assert len(usage_entities) == 3


def test_release_qa_accepts_cell_grain_query_model_safety_rows(
    tmp_path: Path,
) -> None:
    paths = _raw_inputs(tmp_path, include_query_artifacts=True)
    pd.DataFrame(
        [
            {
                "sample_id": sample_id,
                "model_id": "MODEL-1",
                "query_region_id": "QUERY-ACTIVE",
                **_query_safety(),
            }
            for sample_id in ("CELL-1", "CELL-2")
        ]
    ).to_csv(paths["query_models"], index=False, lineterminator="\n")

    report, _ = run_release_qa_from_raw_inputs(paths)

    assert report.ready is True
    assert {
        finding.entity_id
        for finding in report.findings
        if finding.check_id == "query_model_eligible_for_fpps"
    } >= {"CELL-1", "CELL-2"}


def _raw_inputs(
    tmp_path: Path,
    *,
    include_query_artifacts: bool = False,
) -> dict[str, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    source_assets = tmp_path / "source_assets.csv"
    pd.DataFrame(
        [
            {
                "asset_id": "S1-PRE",
                "event_id": "E1",
                "asset_role": "pre_event",
                "product_id": "PRODUCT-PRE",
                "acquisition_time": "2024-09-01T00:00:00Z",
                "processing_allowed": True,
                "label_derivation_allowed": True,
            },
            {
                "asset_id": "S1-EVENT",
                "event_id": "E1",
                "asset_role": "post_event",
                "product_id": "PRODUCT-EVENT",
                "acquisition_time": "2024-09-15T00:00:00Z",
                "processing_allowed": True,
                "label_derivation_allowed": True,
            },
        ]
    ).to_csv(source_assets, index=False, lineterminator="\n")

    assignments = tmp_path / "dataset_assignments.csv"
    pd.DataFrame(
        [
            {
                "region_id": "TRAIN-1",
                "overlap_group": "G-TRAIN",
                "dataset_role": "training_and_query_pool",
            },
            {
                "region_id": "TEST-1",
                "overlap_group": "G-TEST",
                "dataset_role": "untouched_geographic_test",
            },
        ]
    ).to_csv(assignments, index=False, lineterminator="\n")

    usage = tmp_path / "usage_records.csv"
    pd.DataFrame(
        [
            {"region_id": "TRAIN-1", "purpose": "training"},
            {"region_id": "TEST-1", "purpose": "final_evaluation"},
        ]
    ).to_csv(usage, index=False, lineterminator="\n")

    annotations = tmp_path / "annotations.jsonl"
    append_annotation_record(annotations, _annotation())

    binary = tmp_path / "binary_training_rows.csv"
    pd.DataFrame(
        [
            {
                "query_region_id": "TRAIN-1",
                "cell_id": "CELL-1",
                "label_code": 1,
                "binary_target": 1,
            }
        ]
    ).to_csv(binary, index=False, lineterminator="\n")

    paths = {
        "source_assets": source_assets,
        "dataset_assignments": assignments,
        "usage_records": usage,
        "annotations": annotations,
        "binary_training_rows": binary,
    }
    if include_query_artifacts:
        query_models = tmp_path / "query_models.csv"
        pd.DataFrame([{"model_id": "MODEL-1", **_query_safety()}]).to_csv(
            query_models, index=False, lineterminator="\n"
        )
        query_records = tmp_path / "query_records.csv"
        pd.DataFrame(
            [
                {
                    "query_region_id": "QUERY-ACTIVE",
                    "round_id": "R1",
                    "selected": True,
                    "selection_lane": "active",
                    "sampling_stratum": "E1|urban",
                    "sampling_stratum_population": 4,
                    "sampling_stratum_quota": 1,
                    "inclusion_probability": 0.25,
                    **_query_safety(),
                },
                {
                    "query_region_id": "QUERY-RANDOM",
                    "round_id": "R1",
                    "selected": True,
                    "selection_lane": "random_control",
                    "sampling_stratum": "E1|forest",
                    "sampling_stratum_population": 4,
                    "sampling_stratum_quota": 1,
                    "inclusion_probability": 0.25,
                    **_query_safety(),
                },
            ]
        ).to_csv(query_records, index=False, lineterminator="\n")
        paths["query_models"] = query_models
        paths["query_records"] = query_records
    return paths


def _query_safety() -> dict[str, object]:
    return {
        "model_purpose": "query_ranking",
        "eligible_for_review_queue": True,
        "eligible_for_training_after_human_review": "conditional",
        "query_model_only": True,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }


def _annotation() -> AnnotationRecord:
    start = datetime(2024, 9, 16, tzinfo=timezone.utc)
    return AnnotationRecord(
        annotation_id="ANN-1",
        event_id="E1",
        tile_id="TILE-1",
        query_region_id="TRAIN-1",
        reviewer_id="RV-A",
        reviewer_revision=1,
        primary_class=LabelClass.TEMPORARY_FLOOD,
        confidence="high",
        ambiguity_reason_codes=(),
        evidence_layers_used=("pre_vv", "event_vv"),
        review_complete=True,
        reviewed_extent="POLYGON ((0 0, 1 0, 1 1, 0 0))",
        geometry="POLYGON ((0 0, 1 0, 1 1, 0 0))",
        review_started_at=start,
        review_finished_at=start + timedelta(minutes=1),
        protocol_version="protocol_v1",
        tool_version="qgis_v1",
        model_predictions_visible=False,
        other_reviewer_annotations_visible=False,
        created_at_utc=start + timedelta(minutes=2),
        locked_at_utc=start + timedelta(minutes=3),
    )


def _base_receipt(report: object) -> dict[str, object]:
    annotation = _annotation()
    return {
        "artifact_schema": RELEASE_QA_RECEIPT_SCHEMA,
        "qa_protocol_version": "release_qa_v1",
        "qa_report_sha256": qa_report_content_sha256(report),  # type: ignore[arg-type]
        "source_annotation_ids": [annotation.annotation_id],
        "source_annotation_sha256_by_id": {
            annotation.annotation_id: annotation_content_sha256(annotation)
        },
        "reviewer_raster_bindings": "preserved-by-workflow-base-receipt",
    }


def _receipt_hash(receipt: dict[str, object]) -> str:
    content = dict(receipt)
    content.pop("receipt_sha256")
    encoded = json.dumps(
        content,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
