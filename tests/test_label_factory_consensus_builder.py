from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

from floodguard.label_factory.adjudication import (
    append_adjudication_record,
    build_adjudication_queue,
    build_adjudication_record,
    load_adjudication_log,
    pair_locked_annotations,
)
from floodguard.label_factory.annotation_rasterization import (
    canonical_geometry_parts_payload,
    write_rasterized_annotation_outputs,
)
from floodguard.label_factory.annotations import (
    AnnotationRecord,
    LabelClass,
    append_annotation_record,
    load_annotation_log,
)
from floodguard.label_factory.consensus_builder import (
    ConsensusBuilderError,
    write_adjudicator_redraw_outputs,
    write_consensus_outputs,
)
from floodguard.label_factory.review_workflow import (
    ReviewWorkflowError,
    _validate_consensus_builder_receipt,
    load_adjudication_queue_csv,
    write_adjudication_queue_csv,
)


pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("shapely") is None,
    reason="optional geo dependency is not installed",
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_accept_a_produces_freeze_bound_consensus_and_preserves_255(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path, outcome="accept_a")
    outputs = _build(case, tmp_path)

    cells = pd.read_csv(outputs.final_cells, keep_default_na=False)
    assert cells["label_code"].tolist() == [0, 255, 0, 255]
    assert cells["source_annotation_id"].eq("").all()
    assert cells["source_adjudication_id"].eq("ADJ-1").all()
    assert "eligible_for_query_model_training" not in cells
    assert "eligible_for_fpps" not in cells

    lineage = json.loads(outputs.raster_lineage.read_text(encoding="utf-8"))
    receipt = json.loads(outputs.consensus_receipt.read_text(encoding="utf-8"))
    unsigned = dict(receipt)
    declared = unsigned.pop("receipt_sha256")
    assert declared == _json_sha256(unsigned)
    assert lineage["consensus_builder_receipt"] == receipt
    assert set(lineage["rasters"]) == {"final_cells"}
    assert receipt["query_receipts"][0]["output_raster_name"] == "final_cells"
    assert receipt["eligible_for_query_model_training"] is False
    assert lineage["eligible_for_query_model_training"] is False
    assert receipt["query_receipts"][0]["verified_against_final_geometry"] is True
    assert json.loads(outputs.label_content.read_text(encoding="utf-8")) == {
        "QUERY-1": [0, 255, 0, 255]
    }
    resolution = load_adjudication_log(case["adjudication_log"])[0]
    pair = pair_locked_annotations(
        load_annotation_log(case["annotation_log"]),
        reviewer_a_id="RV-A",
        reviewer_b_id="RV-B",
    )[0]
    _validate_consensus_builder_receipt(
        receipt,
        resolutions_by_query={(resolution.event_id, resolution.query_region_id): resolution},
        pairs=[pair],
        queue_items=load_adjudication_queue_csv(case["queue"]),
        reviewer_cell_hashes={
            "ANN-A": _file_hash(case["a_cells"]),
            "ANN-B": _file_hash(case["b_cells"]),
        },
        lineage=lineage,
        consensus_source_artifact_paths=_source_paths(case),
        combined={
            "QUERY-1": list(zip(cells["cell_id"], cells["label_code"], strict=True))
        },
        raster_by_query={"QUERY-1": "final_cells"},
        grid_contract_sha256="a" * 64,
        observed_raster_hashes={"final_cells": _file_hash(outputs.final_cells)},
    )


def test_uncertain_uses_only_intersection_of_explicit_review_support(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path, outcome="uncertain")
    outputs = _build(case, tmp_path)
    cells = pd.read_csv(outputs.final_cells)

    assert cells["label_code"].tolist() == [3, 255, 3, 255]
    lineage = json.loads(outputs.raster_lineage.read_text(encoding="utf-8"))
    assert lineage["consensus_builder_receipt"]["receipt_sha256"]
    receipt = json.loads(outputs.consensus_receipt.read_text(encoding="utf-8"))
    assert receipt["non_geometry_adjudication_receipts"][0]["derivation_rule"] == (
        "class_override_with_a_b_reviewed_support_intersection"
    )


def test_no_queue_requires_exact_a_b_cells_and_records_both_sources(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path, outcome=None)
    outputs = _build(case, tmp_path)
    cells = pd.read_csv(outputs.final_cells, keep_default_na=False)

    assert cells["label_code"].tolist() == [0, 255, 0, 255]
    assert cells["source_annotation_id"].eq("ANN-A").all()
    assert cells["source_adjudication_id"].eq("").all()
    assert cells["source_support_annotation_ids"].eq("ANN-A;ANN-B").all()
    lineage = json.loads(outputs.raster_lineage.read_text(encoding="utf-8"))
    assert lineage["consensus_builder_receipt"]["direct_consensus_receipts"]
    receipt = json.loads(outputs.consensus_receipt.read_text(encoding="utf-8"))
    assert receipt["direct_consensus_receipts"][0]["reviewer_cells_exactly_equal"] is True


def test_direct_consensus_receipt_section_cannot_be_resigned_after_tamper(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path, outcome=None)
    outputs = _build(case, tmp_path)
    cells = pd.read_csv(outputs.final_cells)
    lineage = json.loads(outputs.raster_lineage.read_text(encoding="utf-8"))
    receipt = lineage["consensus_builder_receipt"]
    receipt["direct_consensus_receipts"][0]["reviewer_cells_exactly_equal"] = False
    receipt["receipt_sha256"] = _json_sha256(
        {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    )
    pair = pair_locked_annotations(
        load_annotation_log(case["annotation_log"]),
        reviewer_a_id="RV-A",
        reviewer_b_id="RV-B",
    )[0]

    with pytest.raises(ReviewWorkflowError, match="do not exactly reproduce"):
        _validate_consensus_builder_receipt(
            receipt,
            resolutions_by_query={},
            pairs=[pair],
            queue_items=(),
            reviewer_cell_hashes={
                "ANN-A": _file_hash(case["a_cells"]),
                "ANN-B": _file_hash(case["b_cells"]),
            },
            lineage=lineage,
            consensus_source_artifact_paths=_source_paths(case),
            combined={
                "QUERY-1": list(zip(cells["cell_id"], cells["label_code"], strict=True))
            },
            raster_by_query={"QUERY-1": "final_cells"},
            grid_contract_sha256="a" * 64,
            observed_raster_hashes={"final_cells": _file_hash(outputs.final_cells)},
        )


def test_tampered_reviewer_cells_are_rejected_even_with_rehashed_manifest(
    tmp_path: Path,
) -> None:
    case = _case(tmp_path, outcome="accept_a")
    cells = pd.read_csv(case["a_cells"])
    cells.loc[0, "label_code"] = 1
    cells.loc[0, "label_class"] = "temporary_flood"
    cells.to_csv(case["a_cells"], index=False, lineterminator="\n")
    manifest = json.loads(case["a_manifest"].read_text(encoding="utf-8"))
    manifest["cell_labels_sha256"] = _file_hash(case["a_cells"])
    case["a_manifest"].write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )

    with pytest.raises(ConsensusBuilderError, match="locked-geometry raster"):
        _build(case, tmp_path)


def test_redraw_requires_exact_locked_geometry_cells(tmp_path: Path) -> None:
    case = _case(tmp_path, outcome="redraw")
    _write_redraw(case)
    outputs = _build(case, tmp_path)
    cells = pd.read_csv(outputs.final_cells)
    assert cells["label_code"].tolist() == [255, 1, 255, 1]

    bad = _case(tmp_path / "bad", outcome="redraw")
    _write_redraw(bad, tamper=True)
    with pytest.raises(ConsensusBuilderError, match="adjudication geometry"):
        _build(bad, tmp_path / "bad")


def test_redraw_producer_requires_redraw_and_is_immutable(tmp_path: Path) -> None:
    no_redraw = _case(tmp_path / "no-redraw", outcome="accept_a")
    with pytest.raises(ConsensusBuilderError, match="no locked redraw"):
        write_adjudicator_redraw_outputs(
            adjudication_log_path=no_redraw["adjudication_log"],
            query_manifest_path=no_redraw["query"],
            cell_output_path=tmp_path / "no-redraw.csv",
            manifest_output_path=tmp_path / "no-redraw.json",
        )

    redraw = _case(tmp_path / "redraw", outcome="redraw")
    _write_redraw(redraw)
    manifest = json.loads(Path(redraw["redraw_manifest"]).read_text(encoding="utf-8"))
    assert manifest["source_adjudication_log_sha256"] == _file_hash(
        Path(redraw["adjudication_log"])
    )
    with pytest.raises(ConsensusBuilderError, match="already exist"):
        write_adjudicator_redraw_outputs(
            adjudication_log_path=redraw["adjudication_log"],
            query_manifest_path=redraw["query"],
            cell_output_path=redraw["redraw_cells"],
            manifest_output_path=redraw["redraw_manifest"],
        )


def test_redraw_and_consensus_cli_help_document_authoritative_inputs() -> None:
    for script, expected in (
        ("rasterize_adjudicator_redraw.py", "--adjudication-log"),
        ("build_label_factory_consensus_cells.py", "canonical empty bytes"),
    ):
        run = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / script), "--help"],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert run.returncode == 0
        assert expected in run.stdout


def test_consensus_outputs_are_immutable(tmp_path: Path) -> None:
    case = _case(tmp_path, outcome="accept_b")
    _build(case, tmp_path)
    with pytest.raises(ConsensusBuilderError, match="immutable"):
        _build(case, tmp_path)


def test_missing_adjudication_log_is_canonical_empty_only_for_empty_queue(
    tmp_path: Path,
) -> None:
    direct = _case(tmp_path / "direct", outcome=None)
    Path(direct["adjudication_log"]).unlink()
    outputs = _build(direct, tmp_path / "direct")
    receipt = json.loads(outputs.consensus_receipt.read_text(encoding="utf-8"))
    assert receipt["input_artifact_sha256"]["adjudication_log"] == hashlib.sha256(
        b""
    ).hexdigest()
    assert not Path(direct["adjudication_log"]).exists()

    queued = _case(tmp_path / "queued", outcome="accept_a")
    Path(queued["adjudication_log"]).unlink()
    with pytest.raises(ConsensusBuilderError, match="required.*non-empty"):
        _build(queued, tmp_path / "queued")


def test_partial_output_write_is_rolled_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _case(tmp_path, outcome="accept_a")
    original_open = Path.open

    def failing_open(path: Path, mode: str = "r", *args: object, **kwargs: object):
        if path.name == "lineage.json" and mode == "xb":
            raise OSError("simulated output failure")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", failing_open)
    with pytest.raises(OSError, match="simulated"):
        _build(case, tmp_path)
    assert not (tmp_path / "final.csv").exists()
    assert not (tmp_path / "lineage.json").exists()
    assert not (tmp_path / "labels.json").exists()
    assert not (tmp_path / "receipt.json").exists()


def _case(root: Path, *, outcome: str | None) -> dict[str, Path | str | None]:
    root.mkdir(parents=True, exist_ok=True)
    query = pd.DataFrame([_query_row()])
    query_path = root / "queries.csv"
    query.to_csv(query_path, index=False, lineterminator="\n")
    a_parts = _parts("ANN-A", 0)
    b_parts = _parts("ANN-B", 0 if outcome is None else 1)
    a = _annotation("ANN-A", "RV-A", LabelClass.DRY_LAND, a_parts)
    b = _annotation(
        "ANN-B",
        "RV-B",
        LabelClass.DRY_LAND if outcome is None else LabelClass.TEMPORARY_FLOOD,
        b_parts,
    )
    annotation_log = root / "annotations.jsonl"
    append_annotation_record(annotation_log, a)
    append_annotation_record(annotation_log, b)
    a_cells, a_manifest = root / "a.csv", root / "a.json"
    b_cells, b_manifest = root / "b.csv", root / "b.json"
    write_rasterized_annotation_outputs(
        [a], query_path, a_parts, cell_output_path=a_cells, manifest_output_path=a_manifest
    )
    write_rasterized_annotation_outputs(
        [b], query_path, b_parts, cell_output_path=b_cells, manifest_output_path=b_manifest
    )
    pair = pair_locked_annotations(
        [a, b], reviewer_a_id="RV-A", reviewer_b_id="RV-B"
    )[0]
    queue = build_adjudication_queue([pair], created_at_utc=_now())
    queue_path = root / "queue.csv"
    write_adjudication_queue_csv(queue, queue_path)
    adjudication_log = root / "adjudications.jsonl"
    adjudication_log.touch()
    if outcome is not None:
        kwargs: dict[str, object] = {}
        if outcome == "redraw":
            kwargs.update(
                final_primary_class=LabelClass.TEMPORARY_FLOOD,
                final_geometry="POLYGON ((10 0, 20 0, 20 20, 10 20, 10 0))",
            )
        resolution = build_adjudication_record(
            queue[0],
            pair,
            adjudication_id="ADJ-1",
            adjudicator_id="RV-C",
            outcome=outcome,
            ambiguity_reason_codes=("class_disagreement",),
            resolved_at_utc=_now(),
            locked_at_utc=_now(),
            protocol_version="protocol_v1",
            **kwargs,
        )
        append_adjudication_record(adjudication_log, resolution)
    return {
        "root": root,
        "annotation_log": annotation_log,
        "query": query_path,
        "a_cells": a_cells,
        "a_manifest": a_manifest,
        "b_cells": b_cells,
        "b_manifest": b_manifest,
        "queue": queue_path,
        "adjudication_log": adjudication_log,
        "outcome": outcome,
    }


def _build(case: dict[str, Path | str | None], root: Path):
    return write_consensus_outputs(
        annotation_log_path=case["annotation_log"],
        reviewer_a_id="RV-A",
        reviewer_b_id="RV-B",
        reviewer_a_cells_path=case["a_cells"],
        reviewer_a_manifest_path=case["a_manifest"],
        reviewer_b_cells_path=case["b_cells"],
        reviewer_b_manifest_path=case["b_manifest"],
        adjudication_queue_path=case["queue"],
        adjudication_log_path=case["adjudication_log"],
        query_manifest_path=case["query"],
        redraw_cells_path=case.get("redraw_cells"),
        redraw_manifest_path=case.get("redraw_manifest"),
        final_cells_path=root / "final.csv",
        raster_lineage_path=root / "lineage.json",
        label_content_path=root / "labels.json",
        consensus_receipt_path=root / "receipt.json",
    )


def _source_paths(
    case: dict[str, Path | str | None],
) -> dict[str, Path | str]:
    paths: dict[str, Path | str] = {
        "annotation_log": case["annotation_log"],
        "reviewer_a_cells": case["a_cells"],
        "reviewer_a_manifest": case["a_manifest"],
        "reviewer_b_cells": case["b_cells"],
        "reviewer_b_manifest": case["b_manifest"],
        "adjudication_queue": case["queue"],
        "adjudication_log": case["adjudication_log"],
        "query_manifest": case["query"],
    }  # type: ignore[dict-item]
    if case.get("redraw_cells") is not None:
        paths["redraw_cells"] = case["redraw_cells"]  # type: ignore[assignment]
        paths["redraw_manifest"] = case["redraw_manifest"]  # type: ignore[assignment]
    return paths


def _query_row() -> dict[str, object]:
    return {
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
        "grid_contract_sha256": "a" * 64,
        "source_registry_sha256": "b" * 64,
        "eligible_for_agreement": True,
        "eligible_for_query_model_training": False,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
        "source_timestamp": "2024-09-15T23:16:01Z",
        "assumptions": "Synthetic projected test query only.",
    }


def _parts(annotation_id: str, class_code: int) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "annotation_id": annotation_id,
                "geometry_part_id": "LEFT",
                "class_code": class_code,
                "geometry_wkt": "POLYGON ((0 0, 10 0, 10 20, 0 20, 0 0))",
                "fill_unpainted_with_primary_class": False,
            }
        ]
    )


def _annotation(
    annotation_id: str,
    reviewer_id: str,
    label: LabelClass,
    parts: pd.DataFrame,
) -> AnnotationRecord:
    now = _now()
    return AnnotationRecord(
        annotation_id=annotation_id,
        event_id="TH-MAESAI-2024-09",
        tile_id="TILE-1",
        query_region_id="QUERY-1",
        reviewer_id=reviewer_id,
        reviewer_revision=1,
        primary_class=label,
        confidence="high",
        ambiguity_reason_codes=(),
        evidence_layers_used=("pre_event_vv", "event_time_vv"),
        review_complete=True,
        reviewed_extent="POLYGON ((0 0, 10 0, 10 20, 0 20, 0 0))",
        geometry=canonical_geometry_parts_payload(parts),
        review_started_at=now,
        review_finished_at=now + timedelta(minutes=1),
        protocol_version="protocol_v1",
        tool_version="qgis_v1",
        model_predictions_visible=False,
        other_reviewer_annotations_visible=False,
        created_at_utc=now + timedelta(minutes=1),
        locked_at_utc=now + timedelta(minutes=2),
        source_timestamp=now,
        assumptions="Synthetic test review only.",
        grid_contract_sha256="a" * 64,
        source_registry_sha256="b" * 64,
    )


def _write_redraw(
    case: dict[str, Path | str | None], *, tamper: bool = False
) -> None:
    root = Path(case["root"])
    written = write_adjudicator_redraw_outputs(
        adjudication_log_path=case["adjudication_log"],
        query_manifest_path=case["query"],
        cell_output_path=root / "redraw.csv",
        manifest_output_path=root / "redraw.json",
    )
    if tamper:
        cells = pd.read_csv(written.cell_labels)
        cells.loc[0, "label_code"] = 0
        cells.to_csv(written.cell_labels, index=False, lineterminator="\n")
        manifest = json.loads(written.manifest.read_text(encoding="utf-8"))
        manifest["cell_labels_sha256"] = _file_hash(written.cell_labels)
        written.manifest.write_text(
            json.dumps(manifest, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    case["redraw_cells"] = written.cell_labels
    case["redraw_manifest"] = written.manifest


def _frame_hash(frame: pd.DataFrame) -> str:
    text = frame.to_csv(index=False, lineterminator="\n", float_format="%.17g")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def _now() -> datetime:
    return datetime(2024, 9, 16, 1, 0, tzinfo=timezone.utc)
