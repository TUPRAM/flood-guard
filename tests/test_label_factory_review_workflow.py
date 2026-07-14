from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from floodguard.label_factory.adjudication import (
    append_adjudication_record,
    build_adjudication_queue,
    build_adjudication_record,
    pair_locked_annotations,
)
from floodguard.label_factory.annotations import (
    AnnotationRecord,
    LabelClass,
    append_annotation_record,
    load_annotation_log,
)
from floodguard.label_factory.annotations import annotation_content_sha256
from floodguard.label_factory.annotation_rasterization import (
    canonical_geometry_parts_payload,
    write_rasterized_annotation_outputs,
)
from floodguard.label_factory.consensus_builder import write_consensus_outputs
from floodguard.label_factory.calibration import ReviewerCalibrationReceipt
from floodguard.label_factory.feature_schema import get_feature_schema
from floodguard.label_factory.qa import QAFinding, QAReport, QASeverity
from floodguard.label_factory.release_qa import (
    run_release_qa_from_raw_inputs,
    write_release_qa_artifacts_from_raw,
)
from floodguard.label_factory.training_join import build_and_write_training_table
from floodguard.label_factory.review_workflow import (
    REQUIRED_RELEASE_QA_CHECK_IDS,
    ReviewWorkflowError,
    build_bound_agreement_evidence,
    build_release_qa_evidence_manifest,
    compute_cell_level_agreement,
    freeze_reviewed_labelset,
    import_reviewer_annotations,
    parse_completed_review_csv,
    load_labelset_validation_receipt,
    validate_frozen_labelset,
    write_adjudication_queue_csv,
    write_labelset_validation_receipt,
)


def test_import_requires_supplemental_lock_evidence_and_never_invents_it() -> None:
    frame = _completed_review_frame()
    frame = frame.drop(columns=["locked_at_utc"])
    with pytest.raises(ReviewWorkflowError, match="locked_at_utc"):
        parse_completed_review_csv(frame)


def test_completed_template_maps_revision_and_validates_class_and_blinding() -> None:
    frame = _completed_review_frame()

    records = parse_completed_review_csv(frame)

    assert len(records) == 1
    assert records[0].reviewer_revision == 1
    assert records[0].review_stage.value == "primary"
    assert records[0].created_at_utc == datetime(
        2024, 9, 16, 1, 11, tzinfo=timezone.utc
    )

    mismatched = frame.copy()
    mismatched.loc[0, "class_code"] = "0"
    with pytest.raises(ReviewWorkflowError, match="disagree"):
        parse_completed_review_csv(mismatched)

    visible = frame.copy()
    visible.loc[0, "other_reviewer_annotations_visible"] = "true"
    with pytest.raises(ReviewWorkflowError, match="not independently blinded"):
        parse_completed_review_csv(visible)

    malformed = frame.copy()
    malformed.loc[0, "geometry_wkt"] = "THIS IS NOT WKT"
    with pytest.raises(ReviewWorkflowError, match="valid WKT"):
        parse_completed_review_csv(malformed)


def test_completed_geometry_must_remain_inside_original_review_region(tmp_path: Path) -> None:
    bundle = _formal_bundle_files(tmp_path)
    frame = _completed_review_frame()
    frame.loc[0, "geometry_wkt"] = "POLYGON ((-1 0, 1 0, 1 1, -1 0))"
    parts = _geometry_parts()
    parts.loc[0, "geometry_wkt"] = frame.loc[0, "geometry_wkt"]

    with pytest.raises(ReviewWorkflowError, match="outside"):
        parse_completed_review_csv(
            frame,
            expected_review_regions=bundle["review_regions"],
            geometry_parts=parts,
            bundle_manifest=bundle["bundle_manifest"],
            context_layers=bundle["context_layers"],
            allow_ungoverned_fixture=True,
        )


def test_formal_import_requires_exact_query_set_and_bound_geometry_parts(
    tmp_path: Path,
) -> None:
    bundle = _formal_bundle_files(tmp_path, include_second_query=True)
    frame = _completed_review_frame()

    with pytest.raises(ReviewWorkflowError, match="query set"):
        parse_completed_review_csv(
            frame,
            expected_review_regions=bundle["review_regions"],
            geometry_parts=_geometry_parts(),
            bundle_manifest=bundle["bundle_manifest"],
            context_layers=bundle["context_layers"],
            allow_ungoverned_fixture=True,
        )

    single_bundle = _formal_bundle_files(tmp_path / "single")
    with pytest.raises(ReviewWorkflowError, match="geometry-parts"):
        parse_completed_review_csv(
            _completed_review_frame(),
            expected_review_regions=single_bundle["review_regions"],
            bundle_manifest=single_bundle["bundle_manifest"],
            context_layers=single_bundle["context_layers"],
            allow_ungoverned_fixture=True,
        )


def test_formal_import_locks_bundle_context_and_multipart_provenance(
    tmp_path: Path,
) -> None:
    bundle = _formal_bundle_files(tmp_path)
    records = parse_completed_review_csv(
        _completed_review_frame(),
        expected_review_regions=bundle["review_regions"],
        geometry_parts=_geometry_parts(),
        bundle_manifest=bundle["bundle_manifest"],
        context_layers=bundle["context_layers"],
        allow_ungoverned_fixture=True,
    )

    assert records[0].geometry == canonical_geometry_parts_payload(_geometry_parts())
    assert records[0].bundle_manifest_sha256 == hashlib.sha256(
        bundle["bundle_manifest"].read_bytes()
    ).hexdigest()
    assert records[0].context_manifest_sha256 == hashlib.sha256(
        bundle["context_layers"].read_bytes()
    ).hexdigest()
    assert records[0].grid_contract_sha256 == "e" * 64
    assert records[0].source_registry_sha256 == "f" * 64

    unknown = _completed_review_frame()
    unknown.loc[0, "evidence_layers_used"] = "logistic_prediction"
    with pytest.raises(ReviewWorkflowError, match="not approved"):
        parse_completed_review_csv(
            unknown,
            expected_review_regions=bundle["review_regions"],
            geometry_parts=_geometry_parts(),
            bundle_manifest=bundle["bundle_manifest"],
            context_layers=bundle["context_layers"],
            allow_ungoverned_fixture=True,
        )

    wrong_stage = _completed_review_frame()
    wrong_stage.loc[0, "review_stage"] = "secondary"
    with pytest.raises(ReviewWorkflowError, match="stage or purpose"):
        parse_completed_review_csv(
            wrong_stage,
            expected_review_regions=bundle["review_regions"],
            geometry_parts=_geometry_parts(),
            bundle_manifest=bundle["bundle_manifest"],
            context_layers=bundle["context_layers"],
            allow_ungoverned_fixture=True,
        )


def test_formal_import_rejects_fixture_bundle_without_explicit_opt_in(
    tmp_path: Path,
) -> None:
    bundle = _formal_bundle_files(tmp_path)

    with pytest.raises(ReviewWorkflowError, match="governance package"):
        parse_completed_review_csv(
            _completed_review_frame(),
            expected_review_regions=bundle["review_regions"],
            geometry_parts=_geometry_parts(),
            bundle_manifest=bundle["bundle_manifest"],
            context_layers=bundle["context_layers"],
        )


def test_import_appends_to_canonical_hash_chained_log(tmp_path: Path) -> None:
    log = tmp_path / "annotations.jsonl"
    receipt = import_reviewer_annotations(_completed_review_frame(), log)

    assert receipt.imported_count == 1
    assert receipt.imported_annotation_ids == ("ANN-A",)
    assert len(receipt.record_hashes[0]) == 64
    assert load_annotation_log(log)[0].annotation_id == "ANN-A"

    with pytest.raises(ReviewWorkflowError, match="already exist"):
        import_reviewer_annotations(_completed_review_frame(), log)


def test_cell_agreement_uses_real_cells_and_reports_per_query_boundary() -> None:
    a = _annotation("ANN-A", "RV-A", LabelClass.TEMPORARY_FLOOD)
    b = _annotation("ANN-B", "RV-B", LabelClass.DRY_LAND)
    pair = pair_locked_annotations(
        [a, b], reviewer_a_id="RV-A", reviewer_b_id="RV-B"
    )[0]
    rows = []
    labels_a = [0, 1, 1, 0]
    labels_b = [0, 1, 0, 0]
    for annotation, labels in ((a, labels_a), (b, labels_b)):
        for index, label in enumerate(labels):
            rows.append(
                {
                    "annotation_id": annotation.annotation_id,
                    "query_region_id": annotation.query_region_id,
                    "cell_id": f"C{index}",
                    "label_code": label,
                    "row_index": index // 2,
                    "column_index": index % 2,
                    "grid_contract_sha256": "e" * 64,
                }
            )

    result = compute_cell_level_agreement(
        [pair], pd.DataFrame(rows), pixel_size_m=10, boundary_tolerance_m=20
    )

    assert result.total_cell_count == 4
    assert result.aggregate.exact_agreement == pytest.approx(0.75)
    assert result.aggregate.class_metrics(1).dice_f1 == pytest.approx(2 / 3)
    assert result.boundary_metric_query_count == 1
    assert result.per_query[0]["agreement"]["boundary"] is not None
    assert result.region_primary_class_exact_agreement == 0.0

    evidence = build_bound_agreement_evidence(
        result,
        pairs=[pair],
        cell_labels=pd.DataFrame(rows),
        query_strata=pd.DataFrame(
            [{"query_region_id": "QUERY-1", "stratum": "urban"}]
        ),
    )
    assert evidence["artifact_schema"] == "floodguard.reviewer_agreement.v1"
    assert evidence["grid_contract_sha256"] == "e" * 64
    assert evidence["annotation_sha256_by_id"].keys() == {"ANN-A", "ANN-B"}
    assert evidence["per_query"][0]["reviewer_a_cell_artifact_sha256"]

    stratified = compute_cell_level_agreement(
        [pair],
        pd.DataFrame(rows),
        pixel_size_m=10,
        boundary_tolerance_m=20,
        query_strata=pd.DataFrame(
            [{"query_region_id": "QUERY-1", "stratum": "urban"}]
        ),
    )
    assert dict(stratified.critical_strata)["urban"] == pytest.approx(2 / 3)


def test_primary_class_is_not_accepted_as_pixel_agreement() -> None:
    a = _annotation("ANN-A", "RV-A", LabelClass.TEMPORARY_FLOOD)
    b = _annotation("ANN-B", "RV-B", LabelClass.TEMPORARY_FLOOD)
    pair = pair_locked_annotations(
        [a, b], reviewer_a_id="RV-A", reviewer_b_id="RV-B"
    )[0]
    empty_cells = pd.DataFrame(
        columns=["annotation_id", "query_region_id", "cell_id", "label_code"]
    )
    with pytest.raises(ReviewWorkflowError, match="contains no cells"):
        compute_cell_level_agreement([pair], empty_cells)


def test_cell_agreement_rejects_different_reviewed_cell_coverage() -> None:
    a = _annotation("ANN-A", "RV-A", LabelClass.TEMPORARY_FLOOD)
    b = _annotation("ANN-B", "RV-B", LabelClass.TEMPORARY_FLOOD)
    pair = pair_locked_annotations(
        [a, b], reviewer_a_id="RV-A", reviewer_b_id="RV-B"
    )[0]
    cells = pd.DataFrame(
        [
            {"annotation_id": "ANN-A", "query_region_id": "QUERY-1", "cell_id": "C1", "label_code": 1},
            {"annotation_id": "ANN-B", "query_region_id": "QUERY-1", "cell_id": "C2", "label_code": 1},
        ]
    )
    with pytest.raises(ReviewWorkflowError, match="Cell coverage differs"):
        compute_cell_level_agreement([pair], cells)


def test_freeze_blocks_open_adjudication_and_failed_qa(tmp_path: Path) -> None:
    inputs = _freeze_inputs(tmp_path)
    pair = inputs.pop("_pair")
    with pytest.raises(ReviewWorkflowError, match="remain open"):
        freeze_reviewed_labelset(**inputs)

    queue = inputs["queue_items"][0]
    resolution = build_adjudication_record(
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
    inputs["adjudications"] = [resolution]
    inputs["qa_report"] = _qa_report(passed=False)
    with pytest.raises(ReviewWorkflowError, match="blocking failures"):
        freeze_reviewed_labelset(**inputs)


def test_freeze_cannot_hide_disagreement_by_omitting_queue_row(tmp_path: Path) -> None:
    inputs = _freeze_inputs(tmp_path)
    inputs.pop("_pair")
    inputs["queue_items"] = []
    with pytest.raises(ReviewWorkflowError, match="exactly cover"):
        freeze_reviewed_labelset(**inputs)


def test_freeze_and_validation_bind_human_sources_qa_content_and_raster(
    tmp_path: Path,
) -> None:
    inputs = _freeze_inputs(tmp_path)
    pair = inputs.pop("_pair")
    queue = inputs["queue_items"][0]
    resolution = build_adjudication_record(
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
    inputs["adjudications"] = [resolution]

    manifest = freeze_reviewed_labelset(**inputs)

    assert manifest.labelset_id == "mae_sai_labels_v0.1.0"
    assert dict(manifest.raster_sha256_by_name)["final_cells"] == inputs[
        "expected_raster_sha256"
    ]["final_cells"]
    receipt = validate_frozen_labelset(
        manifest_path=inputs["output_path"],
        label_content=inputs["label_content"],
        metadata=inputs["metadata"],
        semantics=inputs["semantics"],
        queue_items=inputs["queue_items"],
        adjudications=inputs["adjudications"],
        qa_report=inputs["qa_report"],
        qa_evidence_manifest=inputs["qa_evidence_manifest"],
        qa_report_path=inputs["qa_report_path"],
        qa_raw_input_paths=inputs["qa_raw_input_paths"],
        reviewer_calibration_receipt=inputs["reviewer_calibration_receipt"],
        agreement_evidence=inputs["agreement_evidence"],
        raster_lineage=inputs["raster_lineage"],
        raster_paths=inputs["raster_paths"],
        expected_raster_sha256=inputs["expected_raster_sha256"],
        consensus_source_artifact_paths=inputs[
            "consensus_source_artifact_paths"
        ],
        annotation_records=inputs["annotation_records"],
        reviewer_a_id="RV-A",
        reviewer_b_id="RV-B",
    )
    assert receipt.open_adjudication_count == 0
    receipt_path = tmp_path / "validation-receipt.json"
    write_labelset_validation_receipt(receipt, receipt_path)
    assert load_labelset_validation_receipt(receipt_path) == receipt
    tampered = json.loads(receipt_path.read_text(encoding="utf-8"))
    tampered["eligible_for_fpps"] = True
    receipt_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ReviewWorkflowError, match="unsafe"):
        load_labelset_validation_receipt(receipt_path)
    with pytest.raises(ReviewWorkflowError, match="cannot be overwritten"):
        freeze_reviewed_labelset(**inputs)


def test_builder_to_freeze_to_training_join_happy_path(tmp_path: Path) -> None:
    inputs = _freeze_inputs(tmp_path, include_adjudication=True)
    inputs.pop("_pair")
    manifest = freeze_reviewed_labelset(**inputs)
    validation = validate_frozen_labelset(
        manifest_path=inputs["output_path"],
        label_content=inputs["label_content"],
        metadata=inputs["metadata"],
        semantics=inputs["semantics"],
        queue_items=inputs["queue_items"],
        adjudications=inputs["adjudications"],
        qa_report=inputs["qa_report"],
        qa_evidence_manifest=inputs["qa_evidence_manifest"],
        qa_report_path=inputs["qa_report_path"],
        qa_raw_input_paths=inputs["qa_raw_input_paths"],
        reviewer_calibration_receipt=inputs["reviewer_calibration_receipt"],
        agreement_evidence=inputs["agreement_evidence"],
        raster_lineage=inputs["raster_lineage"],
        raster_paths=inputs["raster_paths"],
        expected_raster_sha256=inputs["expected_raster_sha256"],
        consensus_source_artifact_paths=inputs[
            "consensus_source_artifact_paths"
        ],
        annotation_records=inputs["annotation_records"],
        reviewer_a_id="RV-A",
        reviewer_b_id="RV-B",
    )
    validation_path = tmp_path / "labelset-validation.json"
    write_labelset_validation_receipt(validation, validation_path)
    cells = pd.read_csv(inputs["raster_paths"]["final_cells"])
    feature_names = get_feature_schema("sar_change_v2").required_feature_names
    feature_rows = []
    for index, cell in enumerate(cells.to_dict("records")):
        row = {
            "sample_id": cell["cell_id"],
            "query_region_id": cell["query_region_id"],
            "cell_id": cell["cell_id"],
            "grid_contract_sha256": cell["grid_contract_sha256"],
            "spatial_group_id": "BLOCK-1",
            "dataset_role": "training_and_query_pool",
            "feature_schema_version": "sar_change_v2",
        }
        row.update(
            {
                name: float(index + feature_index / 10)
                for feature_index, name in enumerate(feature_names)
            }
        )
        feature_rows.append(row)
    features_path = tmp_path / "features.csv"
    pd.DataFrame(feature_rows).to_csv(
        features_path, index=False, lineterminator="\n"
    )
    outputs = build_and_write_training_table(
        labelset_manifest_path=inputs["output_path"],
        release_validation_receipt_path=validation_path,
        final_cell_csv=inputs["raster_paths"]["final_cells"],
        feature_csv=features_path,
        output_directory=tmp_path / "training",
        created_at_utc="2026-07-10T02:00:00Z",
    )
    training = pd.read_csv(outputs.training_csv)

    assert manifest.labelset_id == "mae_sai_labels_v0.1.0"
    assert set(training["binary_target"]) == {0, 1}
    assert training["event_id"].eq("TH-MAESAI-2024-09").all()
    assert training["tile_id"].eq("TILE-1").all()
    assert training["source_registry_sha256"].eq("f" * 64).all()


def test_freeze_requires_exact_latest_source_annotation_ids(tmp_path: Path) -> None:
    inputs = _freeze_inputs(tmp_path)
    pair = inputs.pop("_pair")
    queue = inputs["queue_items"][0]
    inputs["adjudications"] = [
        build_adjudication_record(
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
    ]
    inputs["source_annotation_ids"] = ["ANN-A"]
    with pytest.raises(ReviewWorkflowError, match="exactly name"):
        freeze_reviewed_labelset(**inputs)


def test_freeze_rejects_cross_run_agreement_evidence(tmp_path: Path) -> None:
    inputs = _freeze_inputs(tmp_path)
    pair = inputs.pop("_pair")
    inputs["adjudications"] = [_accept_a_resolution(pair, inputs["queue_items"][0])]
    inputs["agreement_evidence"]["reviewer_a_id"] = "RV-OTHER"

    with pytest.raises(ReviewWorkflowError, match="identities"):
        freeze_reviewed_labelset(**inputs)


def test_freeze_rejects_generic_single_entity_qa_receipt(tmp_path: Path) -> None:
    inputs = _freeze_inputs(tmp_path)
    pair = inputs.pop("_pair")
    inputs["adjudications"] = [_accept_a_resolution(pair, inputs["queue_items"][0])]
    inputs["qa_evidence_manifest"]["source_product_ids"] = ["fixture"]

    with pytest.raises(ReviewWorkflowError, match="pre- and event-time"):
        freeze_reviewed_labelset(**inputs)


def test_freeze_rejects_raw_qa_source_tamper_after_receipt_creation(
    tmp_path: Path,
) -> None:
    inputs = _freeze_inputs(tmp_path, include_adjudication=True)
    inputs.pop("_pair")
    source_path = inputs["qa_raw_input_paths"]["source_assets"]
    sources = pd.read_csv(source_path)
    sources.loc[0, "processing_allowed"] = False
    sources.to_csv(source_path, index=False, lineterminator="\n")

    with pytest.raises(ReviewWorkflowError, match="Raw release-QA evidence"):
        freeze_reviewed_labelset(**inputs)


def test_freeze_rejects_missing_raw_qa_role(tmp_path: Path) -> None:
    inputs = _freeze_inputs(tmp_path, include_adjudication=True)
    inputs.pop("_pair")
    inputs["qa_raw_input_paths"].pop("usage_records")

    with pytest.raises(ReviewWorkflowError, match="missing=.*usage_records"):
        freeze_reviewed_labelset(**inputs)


def test_freeze_rejects_coherent_legacy_qa_receipt_without_raw_provenance(
    tmp_path: Path,
) -> None:
    inputs = _freeze_inputs(tmp_path, include_adjudication=True)
    inputs.pop("_pair")
    legacy_receipt = dict(inputs["qa_evidence_manifest"])
    for field in (
        "qa_assembler_version",
        "qa_validator",
        "qa_validator_version",
        "qa_report_schema_version",
        "qa_report_file_sha256",
        "raw_input_artifacts",
        "raw_input_roles_in_scope",
        "query_models_in_scope",
        "query_records_in_scope",
        "eligible_for_decision_layer",
        "eligible_for_fpps",
        "eligible_for_warning",
        "receipt_sha256",
    ):
        legacy_receipt.pop(field)
    inputs["qa_evidence_manifest"] = legacy_receipt

    with pytest.raises(ReviewWorkflowError, match="receipt_sha256"):
        freeze_reviewed_labelset(**inputs)


def test_queued_query_cannot_bypass_adjudication_with_annotation_cells(
    tmp_path: Path,
) -> None:
    inputs = _freeze_inputs(tmp_path)
    pair = inputs.pop("_pair")
    inputs["adjudications"] = [_accept_a_resolution(pair, inputs["queue_items"][0])]
    raster = inputs["raster_paths"]["final_cells"]
    cells = pd.read_csv(raster, dtype=str, keep_default_na=False)
    cells["source_annotation_id"] = "ANN-A"
    cells["source_adjudication_id"] = ""
    cells.to_csv(raster, index=False, lineterminator="\n")
    _refresh_raster_hash_bindings(inputs)

    with pytest.raises(ReviewWorkflowError, match="exact adjudication id"):
        freeze_reviewed_labelset(**inputs)


@pytest.mark.parametrize(
    ("outcome", "expected_message"),
    [("reject", "must contribute no cells"), ("uncertain", "label_code=3")],
)
def test_outcome_specific_final_cell_lineage_is_fail_closed(
    tmp_path: Path,
    outcome: str,
    expected_message: str,
) -> None:
    inputs = _freeze_inputs(tmp_path)
    pair = inputs.pop("_pair")
    queue = inputs["queue_items"][0]
    kwargs: dict[str, object] = {
        "adjudication_id": "ADJ-1",
        "adjudicator_id": "RV-C",
        "outcome": outcome,
        "ambiguity_reason_codes": ("class_disagreement",),
        "resolved_at_utc": _now(),
        "locked_at_utc": _now(),
        "protocol_version": "protocol_v1",
    }
    if outcome == "reject":
        kwargs["notes"] = "Cloud or invalid evidence; remove query."
    inputs["adjudications"] = [build_adjudication_record(queue, pair, **kwargs)]

    with pytest.raises(ReviewWorkflowError, match=expected_message):
        freeze_reviewed_labelset(**inputs)


def test_accept_or_redraw_requires_bound_consensus_builder_receipt(
    tmp_path: Path,
) -> None:
    inputs = _freeze_inputs(tmp_path)
    pair = inputs.pop("_pair")
    inputs["adjudications"] = [_accept_a_resolution(pair, inputs["queue_items"][0])]
    inputs["raster_lineage"].pop("consensus_builder_receipt")
    inputs["qa_evidence_manifest"]["audited_artifact_sha256"][
        "raster_lineage"
    ] = _json_sha256(inputs["raster_lineage"])

    with pytest.raises(ReviewWorkflowError, match="consensus-builder"):
        freeze_reviewed_labelset(**inputs)


def test_copied_lineage_ids_cannot_authorize_arbitrary_final_cells(
    tmp_path: Path,
) -> None:
    inputs = _freeze_inputs(tmp_path, include_adjudication=True)
    inputs.pop("_pair")
    raster = inputs["raster_paths"]["final_cells"]
    cells = pd.read_csv(raster, dtype=str, keep_default_na=False)
    cells["label_code"] = cells["label_code"].map({"0": "1", "1": "0"})
    cells.to_csv(raster, index=False, lineterminator="\n")
    ordered = cells.sort_values("cell_id", kind="stable")
    inputs["label_content"] = {
        "QUERY-1": [int(value) for value in ordered["label_code"]]
    }
    _rebind_tampered_consensus(inputs, cells)

    with pytest.raises(ReviewWorkflowError, match="do not exactly reproduce"):
        freeze_reviewed_labelset(**inputs)


@pytest.mark.parametrize("field", ["event_id", "tile_id", "source_registry_sha256"])
def test_final_cell_context_must_match_locked_query_lineage(
    tmp_path: Path,
    field: str,
) -> None:
    inputs = _freeze_inputs(tmp_path, include_adjudication=True)
    inputs.pop("_pair")
    raster = inputs["raster_paths"]["final_cells"]
    cells = pd.read_csv(raster, dtype=str, keep_default_na=False)
    cells.loc[0, field] = "0" * 64 if field == "source_registry_sha256" else "OTHER"
    cells.to_csv(raster, index=False, lineterminator="\n")
    _refresh_raster_hash_bindings(inputs)

    with pytest.raises(ReviewWorkflowError, match="event/tile/source registry"):
        freeze_reviewed_labelset(**inputs)


def test_non_geometry_receipt_section_must_reproduce_locked_outcome(
    tmp_path: Path,
) -> None:
    inputs = _freeze_inputs(
        tmp_path,
        built_outcome="uncertain",
        include_adjudication=True,
    )
    inputs.pop("_pair")
    receipt = inputs["raster_lineage"]["consensus_builder_receipt"]
    receipt["non_geometry_adjudication_receipts"][0]["derivation_rule"] = "forged"
    receipt["receipt_sha256"] = _json_sha256(
        {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    )
    inputs["qa_evidence_manifest"]["audited_artifact_sha256"][
        "raster_lineage"
    ] = _json_sha256(inputs["raster_lineage"])

    with pytest.raises(ReviewWorkflowError, match="do not exactly reproduce"):
        freeze_reviewed_labelset(**inputs)


def test_uncertain_release_preserves_explicit_255_cells(tmp_path: Path) -> None:
    inputs = _freeze_inputs(
        tmp_path,
        built_outcome="uncertain",
        include_adjudication=True,
    )
    inputs.pop("_pair")

    manifest = freeze_reviewed_labelset(**inputs)
    assert manifest.labelset_id == "mae_sai_labels_v0.1.0"


def test_non_rejected_adjudication_cannot_release_only_255_cells(
    tmp_path: Path,
) -> None:
    inputs = _freeze_inputs(tmp_path)
    pair = inputs.pop("_pair")
    inputs["adjudications"] = [
        build_adjudication_record(
            inputs["queue_items"][0],
            pair,
            adjudication_id="ADJ-1",
            adjudicator_id="RV-C",
            outcome="unobservable",
            ambiguity_reason_codes=("class_disagreement",),
            resolved_at_utc=_now(),
            locked_at_utc=_now(),
            protocol_version="protocol_v1",
        )
    ]
    labels = [255, 255, 255, 255]
    raster = inputs["raster_paths"]["final_cells"]
    cells = pd.read_csv(raster, dtype=str, keep_default_na=False)
    cells["label_code"] = labels
    cells.to_csv(raster, index=False, lineterminator="\n")
    lineage = inputs["raster_lineage"]
    lineage["rasters"]["final_cells"]["class_counts"] = {"255": 4}
    inputs["label_content"] = {"QUERY-1": labels}
    _refresh_raster_hash_bindings(inputs)

    with pytest.raises(ReviewWorkflowError, match="at least one reviewed non-255"):
        freeze_reviewed_labelset(**inputs)


def _freeze_inputs(
    tmp_path: Path,
    *,
    built_outcome: str = "accept_a",
    include_adjudication: bool = False,
) -> dict[str, object]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    a = _freeze_annotation("ANN-A", "RV-A", LabelClass.TEMPORARY_FLOOD)
    b = _freeze_annotation("ANN-B", "RV-B", LabelClass.DRY_LAND)
    pair = pair_locked_annotations(
        [a, b], reviewer_a_id="RV-A", reviewer_b_id="RV-B"
    )[0]
    queue = build_adjudication_queue([pair], created_at_utc=_now())
    grid_hash = "e" * 64
    query_path = tmp_path / "queries.csv"
    pd.DataFrame(
        [
            {
                "query_region_id": "QUERY-1",
                "event_id": "TH-MAESAI-2024-09",
                "tile_id": "TILE-1",
                "bbox_min_x": 0.0,
                "bbox_min_y": 0.0,
                "bbox_max_x": 20.0,
                "bbox_max_y": 20.0,
                "query_size_pixels": 2,
                "crs": "EPSG:32647",
                "grid_id": "UTM47N_10M_TEST",
                "grid_contract_sha256": grid_hash,
                "source_registry_sha256": "f" * 64,
                "eligible_for_agreement": True,
                "eligible_for_query_model_training": False,
                "eligible_for_decision_layer": False,
                "eligible_for_fpps": False,
                "eligible_for_warning": False,
                "source_timestamp": "2024-09-16T00:00:00Z",
                "assumptions": "Synthetic release-gate fixture only.",
            }
        ]
    ).to_csv(query_path, index=False, lineterminator="\n")
    annotation_log = tmp_path / "annotations.jsonl"
    append_annotation_record(annotation_log, a)
    append_annotation_record(annotation_log, b)
    a_cells, a_manifest = tmp_path / "a-cells.csv", tmp_path / "a-cells.json"
    b_cells, b_manifest = tmp_path / "b-cells.csv", tmp_path / "b-cells.json"
    write_rasterized_annotation_outputs(
        [a],
        query_path,
        _freeze_geometry_parts("ANN-A", reverse=False),
        cell_output_path=a_cells,
        manifest_output_path=a_manifest,
    )
    write_rasterized_annotation_outputs(
        [b],
        query_path,
        _freeze_geometry_parts("ANN-B", reverse=True),
        cell_output_path=b_cells,
        manifest_output_path=b_manifest,
    )
    queue_path = tmp_path / "queue.csv"
    write_adjudication_queue_csv(queue, queue_path)
    resolution = build_adjudication_record(
        queue[0],
        pair,
        adjudication_id="ADJ-1",
        adjudicator_id="RV-C",
        outcome=built_outcome,
        ambiguity_reason_codes=("class_disagreement",),
        resolved_at_utc=_now(),
        locked_at_utc=_now(),
        protocol_version="protocol_v1",
    )
    adjudication_log = tmp_path / "adjudications.jsonl"
    append_adjudication_record(adjudication_log, resolution)
    raster = tmp_path / "labels.csv"
    lineage_path = tmp_path / "lineage.json"
    label_content_path = tmp_path / "label-content.json"
    receipt_path = tmp_path / "consensus-receipt.json"
    write_consensus_outputs(
        annotation_log_path=annotation_log,
        reviewer_a_id="RV-A",
        reviewer_b_id="RV-B",
        reviewer_a_cells_path=a_cells,
        reviewer_a_manifest_path=a_manifest,
        reviewer_b_cells_path=b_cells,
        reviewer_b_manifest_path=b_manifest,
        adjudication_queue_path=queue_path,
        adjudication_log_path=adjudication_log,
        query_manifest_path=query_path,
        final_cells_path=raster,
        raster_lineage_path=lineage_path,
        label_content_path=label_content_path,
        consensus_receipt_path=receipt_path,
    )
    digest = hashlib.sha256(raster.read_bytes()).hexdigest()
    lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
    labels = json.loads(label_content_path.read_text(encoding="utf-8"))
    agreement = _agreement_evidence(
        a,
        b,
        grid_hash=grid_hash,
        cell_hashes={
            "ANN-A": hashlib.sha256(a_cells.read_bytes()).hexdigest(),
            "ANN-B": hashlib.sha256(b_cells.read_bytes()).hexdigest(),
        },
    )
    source_assets_path = tmp_path / "qa-source-assets.csv"
    pd.DataFrame(
        [
            {
                "asset_id": "S1-PRE-001",
                "event_id": "TH-MAESAI-2024-09",
                "asset_role": "pre_event",
                "product_id": "S1-PRE-PRODUCT",
                "acquisition_time": "2024-09-01T00:00:00Z",
                "processing_allowed": True,
                "label_derivation_allowed": True,
            },
            {
                "asset_id": "S1-EVENT-001",
                "event_id": "TH-MAESAI-2024-09",
                "asset_role": "post_event",
                "product_id": "S1-EVENT-PRODUCT",
                "acquisition_time": "2024-09-15T00:00:00Z",
                "processing_allowed": True,
                "label_derivation_allowed": True,
            },
        ]
    ).to_csv(source_assets_path, index=False, lineterminator="\n")
    assignments_path = tmp_path / "qa-dataset-assignments.csv"
    pd.DataFrame(
        [
            {
                "region_id": "QUERY-1",
                "overlap_group": "QUERY-1",
                "dataset_role": "training_and_query_pool",
            }
        ]
    ).to_csv(assignments_path, index=False, lineterminator="\n")
    usage_path = tmp_path / "qa-usage-records.csv"
    pd.DataFrame(
        [{"region_id": "QUERY-1", "purpose": "training"}]
    ).to_csv(usage_path, index=False, lineterminator="\n")
    binary_rows_path = tmp_path / "qa-binary-training-rows.csv"
    final_cells = pd.read_csv(raster, dtype=str, keep_default_na=False)
    binary_rows = []
    for row in final_cells.to_dict(orient="records"):
        label_code = int(row["label_code"])
        if label_code not in {0, 1, 2}:
            continue
        binary_rows.append(
            {
                "query_region_id": row["query_region_id"],
                "cell_id": row["cell_id"],
                "label_code": label_code,
                "binary_target": {0: 0, 1: 1, 2: 0}[label_code],
            }
        )
    pd.DataFrame(binary_rows).to_csv(
        binary_rows_path, index=False, lineterminator="\n"
    )
    qa_raw_input_paths = {
        "source_assets": source_assets_path,
        "dataset_assignments": assignments_path,
        "usage_records": usage_path,
        "annotations": annotation_log,
        "binary_training_rows": binary_rows_path,
    }
    qa_report, _ = run_release_qa_from_raw_inputs(qa_raw_input_paths)
    calibration_receipt = _valid_calibration_receipt()
    base_qa_evidence = build_release_qa_evidence_manifest(
        qa_report=qa_report,
        pairs=[pair],
        agreement_evidence=agreement,
        raster_lineage=lineage,
        raster_hashes={"final_cells": digest},
        reviewer_calibration_receipt=calibration_receipt,
        qa_protocol_version="release_qa_v1",
    )
    qa_report_path = tmp_path / "release-qa.csv"
    qa_evidence_path = tmp_path / "release-qa-receipt.json"
    qa_report, qa_evidence, _, _ = write_release_qa_artifacts_from_raw(
        qa_report=qa_report,
        base_receipt=base_qa_evidence,
        raw_input_paths=qa_raw_input_paths,
        qa_report_path=qa_report_path,
        qa_receipt_path=qa_evidence_path,
    )
    return {
        "annotation_records": [a, b],
        "reviewer_a_id": "RV-A",
        "reviewer_b_id": "RV-B",
        "queue_items": queue,
        "adjudications": [resolution] if include_adjudication else [],
        "qa_report": qa_report,
        "qa_evidence_manifest": qa_evidence,
        "qa_report_path": qa_report_path,
        "qa_raw_input_paths": qa_raw_input_paths,
        "reviewer_calibration_receipt": calibration_receipt,
        "agreement_evidence": agreement,
        "labelset_name": "mae_sai_labels",
        "version": "0.1.0",
        "change_kind": "initial",
        "label_content": labels,
        "metadata": {"protocol": "protocol_v1", "source_timestamp": "2024-09-16T01:00:00Z"},
        "semantics": {"taxonomy": "flood_label_v1", "grid": "utm_10m_v1"},
        "source_annotation_ids": ["ANN-A", "ANN-B"],
        "raster_paths": {"final_cells": raster},
        "expected_raster_sha256": {"final_cells": digest},
        "consensus_source_artifact_paths": {
            "annotation_log": annotation_log,
            "reviewer_a_cells": a_cells,
            "reviewer_a_manifest": a_manifest,
            "reviewer_b_cells": b_cells,
            "reviewer_b_manifest": b_manifest,
            "adjudication_queue": queue_path,
            "adjudication_log": adjudication_log,
            "query_manifest": query_path,
        },
        "raster_lineage": lineage,
        "output_path": tmp_path / "mae_sai_labels_v0.1.0.json",
        "created_at_utc": _now(),
        "_pair": pair,
    }


def _qa_report(*, passed: bool) -> QAReport:
    source_checks = {
        "source_product_id",
        "source_acquisition_time",
        "rights_processing",
        "rights_label_derivation",
    }
    event_checks = {"pre_post_pair_present", "pre_before_post"}
    findings = []
    for check_id in sorted(REQUIRED_RELEASE_QA_CHECK_IDS):
        entities = (
            ("S1-PRE-001", "S1-EVENT-001")
            if check_id in source_checks
            else (("TH-MAESAI-2024-09",) if check_id in event_checks else ("QUERY-1",))
        )
        for entity_id in entities:
            findings.append(
                QAFinding(
                    check_id=check_id,
                    entity_id=entity_id,
                    passed=passed if check_id == "source_product_id" else True,
                    severity=QASeverity.CRITICAL,
                    message="Explicit unit-test provenance check.",
                    observed=str(passed),
                    expected="True",
                )
            )
    return QAReport(
        findings=tuple(findings)
    )


def _valid_calibration_receipt() -> ReviewerCalibrationReceipt:
    query_ids = tuple(f"CAL-Q{index:02d}" for index in range(1, 9))
    annotation_ids_by_reviewer = tuple(
        (
            reviewer_id,
            tuple(f"CAL-ANN-{reviewer_id}-{query_id}" for query_id in query_ids),
        )
        for reviewer_id in ("RV-A", "RV-B")
    )
    annotation_ids = [
        annotation_id
        for _reviewer_id, ids in annotation_ids_by_reviewer
        for annotation_id in ids
    ]
    per_query = [
        {
            "query_region_id": query_id,
            "comparable_cell_count": 4,
            "temporary_flood_dice": 1.0,
            "temporary_flood_iou": 1.0,
            "cohen_kappa": 1.0,
            "boundary_f1": 1.0,
        }
        for query_id in query_ids
    ]
    metrics = {
        "temporary_flood_dice": 1.0,
        "temporary_flood_iou": 1.0,
        "cohen_kappa": 1.0,
        "mean_boundary_f1": 1.0,
        "critical_strata_dice": {"urban": 1.0},
        "query_count": 8,
        "comparable_cell_count": 32,
        "ignored_cell_count": 0,
        "per_query": per_query,
    }
    values = {
        "reviewer_ids": ("RV-A", "RV-B"),
        "protocol_version": "protocol_v1",
        "taxonomy_version": "flood_label_v1",
        "calibration_completed_at_utc": datetime(
            2024, 9, 16, 0, 0, tzinfo=timezone.utc
        ),
        "formal_review_not_before_utc": datetime(
            2024, 9, 16, 0, 30, tzinfo=timezone.utc
        ),
        "query_manifest_sha256": "0" * 64,
        "query_region_ids": query_ids,
        "annotation_sha256_by_id": tuple(
            (annotation_id, hashlib.sha256(annotation_id.encode()).hexdigest())
            for annotation_id in annotation_ids
        ),
        "annotation_ids_by_reviewer": annotation_ids_by_reviewer,
        "reviewer_cell_sha256_by_reviewer": (
            ("RV-A", "1" * 64),
            ("RV-B", "2" * 64),
        ),
        "reviewer_cell_manifest_sha256_by_reviewer": (
            ("RV-A", "3" * 64),
            ("RV-B", "4" * 64),
        ),
        "calibration_reference_manifest_sha256": "5" * 64,
        "calibration_reference_cells_sha256": "6" * 64,
        "grid_contract_sha256_by_query": tuple(
            (query_id, "7" * 64) for query_id in query_ids
        ),
        "source_registry_sha256_by_query": tuple(
            (query_id, "8" * 64) for query_id in query_ids
        ),
        "source_timestamp_by_query": tuple(
            (query_id, "2024-09-15T23:00:00Z") for query_id in query_ids
        ),
        "metrics_by_reviewer": (("RV-A", metrics), ("RV-B", metrics)),
        "thresholds": (
            ("cohen_kappa", 0.75),
            ("critical_stratum_dice", 0.65),
            ("mean_boundary_f1", 0.70),
            ("temporary_flood_dice", 0.75),
        ),
        "query_strata_sha256": "9" * 64,
        "assumptions": "Synthetic passing calibration receipt for release tests.",
    }
    provisional = ReviewerCalibrationReceipt(**values, receipt_sha256="")
    digest = hashlib.sha256(
        json.dumps(
            provisional.to_dict(include_self_hash=False),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()
    return ReviewerCalibrationReceipt(**values, receipt_sha256=digest)


def _agreement_evidence(
    a: AnnotationRecord,
    b: AnnotationRecord,
    *,
    grid_hash: str,
    cell_hashes: dict[str, str] | None = None,
) -> dict[str, object]:
    boundary = {"f1": 0.90}
    annotation_hashes = {
        a.annotation_id: annotation_content_sha256(a),
        b.annotation_id: annotation_content_sha256(b),
    }
    cell_hashes = cell_hashes or {
        a.annotation_id: "1" * 64,
        b.annotation_id: "2" * 64,
    }
    return {
        "artifact_schema": "floodguard.reviewer_agreement.v1",
        "reviewer_a_id": a.reviewer_id,
        "reviewer_b_id": b.reviewer_id,
        "measurement_unit": "canonical_cell_labels",
        "grid_contract_sha256": grid_hash,
        "query_region_ids": ["QUERY-1"],
        "annotation_sha256_by_id": annotation_hashes,
        "reviewer_cell_artifact_sha256_by_annotation_id": cell_hashes,
        "review_import_provenance_by_annotation_id": {
            record.annotation_id: {
                "bundle_manifest_sha256": record.bundle_manifest_sha256,
                "context_manifest_sha256": record.context_manifest_sha256,
                "grid_contract_sha256": record.grid_contract_sha256,
                "source_registry_sha256": record.source_registry_sha256,
            }
            for record in (a, b)
        },
        "query_count": 1,
        "total_cell_count": 4,
        "boundary_metric_query_count": 1,
        "aggregate": {
            "per_class": {"1": {"dice_f1": 0.90, "iou": 0.82}},
            "cohen_kappa": 0.88,
        },
        "per_query": [
            {
                "event_id": a.event_id,
                "tile_id": a.tile_id,
                "query_region_id": a.query_region_id,
                "reviewer_a_annotation_id": a.annotation_id,
                "reviewer_b_annotation_id": b.annotation_id,
                "reviewer_a_annotation_sha256": annotation_hashes[a.annotation_id],
                "reviewer_b_annotation_sha256": annotation_hashes[b.annotation_id],
                "reviewer_a_cell_artifact_sha256": cell_hashes[a.annotation_id],
                "reviewer_b_cell_artifact_sha256": cell_hashes[b.annotation_id],
                "cell_count": 4,
                "agreement": {"boundary": boundary},
            }
        ],
        "critical_strata": {"urban": 0.80},
    }


def _completed_review_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "annotation_id": "ANN-A",
                "event_id": "TH-MAESAI-2024-09",
                "tile_id": "TILE-1",
                "query_region_id": "QUERY-1",
                "reviewer_id": "RV-A",
                "review_revision": "1",
                "primary_class": "temporary_flood",
                "class_code": "1",
                "confidence": "high",
                "ambiguity_reason_codes": "",
                "evidence_layers_used": "pre_event_vv;event_time_vv;dem_hillshade",
                "review_complete": "true",
                "reviewed_extent_status": "entire_valid_query_core",
                "reviewed_extent": "POLYGON ((0 0, 2 0, 2 2, 0 0))",
                "geometry_wkt": "POLYGON ((0 0, 1 0, 1 1, 0 0))",
                "review_started_at_utc": "2024-09-16T01:00:00Z",
                "review_finished_at_utc": "2024-09-16T01:10:00Z",
                "protocol_version": "protocol_v1",
                "tool_version": "qgis_v1",
                "model_predictions_visible": "false",
                "other_reviewer_annotations_visible": "false",
                "supersedes_annotation_id": "",
                "review_stage": "primary",
                "review_purpose": "acquisition_primary",
                "created_at_utc": "2024-09-16T01:11:00Z",
                "locked_at_utc": "2024-09-16T01:12:00Z",
                "source_timestamp": "2024-09-16T00:00:00Z",
                "assumptions": "Synthetic unit-test review row only.",
            }
        ]
    )


def _annotation(
    annotation_id: str,
    reviewer_id: str,
    primary_class: LabelClass,
) -> AnnotationRecord:
    start = datetime(2024, 9, 16, 1, 0, tzinfo=timezone.utc)
    parts = _geometry_parts(annotation_id=annotation_id)
    return AnnotationRecord(
        annotation_id=annotation_id,
        event_id="TH-MAESAI-2024-09",
        tile_id="TILE-1",
        query_region_id="QUERY-1",
        reviewer_id=reviewer_id,
        reviewer_revision=1,
        primary_class=primary_class,
        confidence="high",
        ambiguity_reason_codes=(),
        evidence_layers_used=("pre_event_vv", "event_time_vv", "dem_hillshade"),
        review_complete=True,
        reviewed_extent="POLYGON ((0 0, 2 0, 2 2, 0 0))",
        geometry=canonical_geometry_parts_payload(parts),
        review_started_at=start,
        review_finished_at=start + timedelta(minutes=10),
        protocol_version="protocol_v1",
        tool_version="qgis_v1",
        model_predictions_visible=False,
        other_reviewer_annotations_visible=False,
        created_at_utc=start + timedelta(minutes=11),
        locked_at_utc=start + timedelta(minutes=12),
        source_timestamp=datetime(2024, 9, 16, 0, 0, tzinfo=timezone.utc),
        assumptions="Synthetic unit-test review only.",
        bundle_manifest_sha256=("a" if reviewer_id == "RV-A" else "b") * 64,
        context_manifest_sha256=("c" if reviewer_id == "RV-A" else "d") * 64,
        grid_contract_sha256="e" * 64,
        source_registry_sha256="f" * 64,
    )


def _freeze_annotation(
    annotation_id: str,
    reviewer_id: str,
    primary_class: LabelClass,
) -> AnnotationRecord:
    start = datetime(2024, 9, 16, 1, 0, tzinfo=timezone.utc)
    parts = _freeze_geometry_parts(
        annotation_id,
        reverse=reviewer_id == "RV-B",
    )
    return AnnotationRecord(
        annotation_id=annotation_id,
        event_id="TH-MAESAI-2024-09",
        tile_id="TILE-1",
        query_region_id="QUERY-1",
        reviewer_id=reviewer_id,
        reviewer_revision=1,
        primary_class=primary_class,
        confidence="high",
        ambiguity_reason_codes=(),
        evidence_layers_used=("pre_event_vv", "event_time_vv"),
        review_complete=True,
        reviewed_extent="entire_query_core",
        geometry=canonical_geometry_parts_payload(parts),
        review_started_at=start,
        review_finished_at=start + timedelta(minutes=10),
        protocol_version="protocol_v1",
        tool_version="qgis_v1",
        model_predictions_visible=False,
        other_reviewer_annotations_visible=False,
        created_at_utc=start + timedelta(minutes=11),
        locked_at_utc=start + timedelta(minutes=12),
        source_timestamp=datetime(2024, 9, 16, 0, 0, tzinfo=timezone.utc),
        assumptions="Synthetic release-gate fixture only.",
        bundle_manifest_sha256=("a" if reviewer_id == "RV-A" else "b") * 64,
        context_manifest_sha256=("c" if reviewer_id == "RV-A" else "d") * 64,
        grid_contract_sha256="e" * 64,
        source_registry_sha256="f" * 64,
    )


def _freeze_geometry_parts(
    annotation_id: str,
    *,
    reverse: bool,
) -> pd.DataFrame:
    left, right = ((1, 0) if reverse else (0, 1))
    return pd.DataFrame(
        [
            {
                "annotation_id": annotation_id,
                "geometry_part_id": "LEFT",
                "class_code": left,
                "geometry_wkt": "POLYGON ((0 0, 10 0, 10 20, 0 20, 0 0))",
                "fill_unpainted_with_primary_class": False,
            },
            {
                "annotation_id": annotation_id,
                "geometry_part_id": "RIGHT",
                "class_code": right,
                "geometry_wkt": "POLYGON ((10 0, 20 0, 20 20, 10 20, 10 0))",
                "fill_unpainted_with_primary_class": False,
            },
        ]
    )


def _now() -> datetime:
    return datetime(2024, 9, 17, 1, 0, tzinfo=timezone.utc)


def _geometry_parts(*, annotation_id: str = "ANN-A") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "annotation_id": annotation_id,
                "geometry_part_id": "PART-1",
                "class_code": 1,
                "geometry_wkt": "POLYGON ((0 0, 1 0, 1 1, 0 0))",
                "fill_unpainted_with_primary_class": False,
            }
        ]
    )


def _formal_bundle_files(
    tmp_path: Path,
    *,
    include_second_query: bool = False,
) -> dict[str, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    processing_receipt_sha256 = "a" * 64
    rows = [
        {
            "event_id": "TH-MAESAI-2024-09",
            "tile_id": "TILE-1",
            "query_region_id": "QUERY-1",
            "bbox_min_x": 0,
            "bbox_min_y": 0,
            "bbox_max_x": 2,
            "bbox_max_y": 2,
            "grid_contract_sha256": "e" * 64,
            "source_registry_sha256": "f" * 64,
            "processing_alignment_receipt_sha256": processing_receipt_sha256,
            "dataset_role": "training_and_query_pool",
        }
    ]
    if include_second_query:
        rows.append(
            {
                **rows[0],
                "tile_id": "TILE-2",
                "query_region_id": "QUERY-2",
                "bbox_min_x": 2,
                "bbox_max_x": 4,
            }
        )
    regions_path = tmp_path / "review_regions.csv"
    pd.DataFrame(rows).to_csv(regions_path, index=False, lineterminator="\n")
    context_path = tmp_path / "context_layers.csv"
    pd.DataFrame(
        [
            {
                "context_layer_id": f"CTX-{index}",
                "event_id": "TH-MAESAI-2024-09",
                "layer_role": role,
                "source_registry_sha256": "f" * 64,
                "source_sha256": str(index + 1) * 64,
                "processed_layer_sha256": str(index + 4) * 64,
                "allowed_for_blinded_review": True,
            }
            for index, role in enumerate(
                ("pre_event_vv", "event_time_vv", "dem_hillshade")
            )
        ]
    ).to_csv(context_path, index=False, lineterminator="\n")
    processing_path = tmp_path / "processing_alignment_receipt.json"
    processing_path.write_text(
        json.dumps({"synthetic_fixture_only": True}) + "\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "bundle_manifest.csv"
    pd.DataFrame(
        [
            {
                "file_name": path.name,
                "bundle_role": role,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "model_predictions_visible": False,
                "review_stage": "primary",
                "review_purpose": "acquisition_primary",
                "governance_package_id": "",
                "governance_package_manifest_sha256": "",
                "governance_package_seal_sha256": "",
                "aligned_context_inventory_sha256": "",
                "grid_validation_receipt_sha256": "",
                "grid_validation_receipt_file_sha256": "",
                "canonical_tile_manifest_file_sha256": "",
                "canonical_query_manifest_file_sha256": "",
                "supported_query_derivation_file_sha256": "",
                "supported_query_derivation_sha256": "",
                "supported_query_csv_sha256": "",
                "governance_binding_status": "synthetic_fixture_only",
                "production_review_eligible": False,
                "processing_alignment_receipt_sha256": processing_receipt_sha256,
                "eligible_for_decision_layer": False,
                "eligible_for_fpps": False,
                "eligible_for_warning": False,
            }
            for path, role in (
                (regions_path, "reviewer_visible_regions"),
                (context_path, "approved_context_source_evidence"),
                (processing_path, "processing_alignment_provenance"),
            )
        ]
    ).to_csv(manifest_path, index=False, lineterminator="\n")
    return {
        "review_regions": regions_path,
        "context_layers": context_path,
        "bundle_manifest": manifest_path,
        "processing_alignment_receipt": processing_path,
    }


def _json_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _accept_a_resolution(pair: object, queue: object) -> object:
    return build_adjudication_record(
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


def _refresh_raster_hash_bindings(inputs: dict[str, object]) -> None:
    raster = inputs["raster_paths"]["final_cells"]
    digest = hashlib.sha256(raster.read_bytes()).hexdigest()
    inputs["expected_raster_sha256"]["final_cells"] = digest
    lineage = inputs["raster_lineage"]
    lineage["rasters"]["final_cells"]["sha256"] = digest
    if "consensus_builder_receipt" in lineage:
        lineage["consensus_builder_receipt"]["output_raster_sha256_by_name"][
            "final_cells"
        ] = digest
    qa_artifacts = inputs["qa_evidence_manifest"]["audited_artifact_sha256"]
    qa_artifacts["label_raster:final_cells"] = digest
    qa_artifacts["raster_lineage"] = _json_sha256(lineage)


def _rebind_tampered_consensus(
    inputs: dict[str, object], cells: pd.DataFrame
) -> None:
    raster = inputs["raster_paths"]["final_cells"]
    digest = hashlib.sha256(raster.read_bytes()).hexdigest()
    counts = {
        str(code): int(count)
        for code, count in pd.to_numeric(cells["label_code"])
        .astype(int)
        .value_counts()
        .sort_index()
        .items()
    }
    lineage = inputs["raster_lineage"]
    lineage["rasters"]["final_cells"].update(
        sha256=digest,
        cell_count=len(cells),
        class_counts=counts,
    )
    receipt = lineage["consensus_builder_receipt"]
    receipt["output_raster_sha256_by_name"] = {"final_cells": digest}
    receipt["class_counts"] = counts
    receipt["final_cell_count"] = len(cells)
    ordered = cells.sort_values("cell_id", kind="stable")
    labeled = [
        {"cell_id": str(row.cell_id), "label_code": int(row.label_code)}
        for row in ordered.itertuples(index=False)
    ]
    receipt["query_receipts"][0]["labeled_cells_sha256"] = _json_sha256(labeled)
    receipt["receipt_sha256"] = _json_sha256(
        {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    )
    inputs["expected_raster_sha256"]["final_cells"] = digest
    qa_artifacts = inputs["qa_evidence_manifest"]["audited_artifact_sha256"]
    qa_artifacts["label_raster:final_cells"] = digest
    qa_artifacts["raster_lineage"] = _json_sha256(lineage)
