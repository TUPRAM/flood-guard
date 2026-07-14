"""Deterministic construction of reviewed consensus cells.

This module is the only bridge from two agreement-only reviewer rasters and
locked adjudication records to the canonical final-cell CSV accepted by label
release.  It deliberately recomputes reviewer geometry-to-cell results from
the locked annotation payloads; source raster manifests are evidence, not
authority.  Unreviewed cells (255) remain unreviewed and are never converted
to dry land by default.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from floodguard.label_factory.adjudication import (
    AdjudicationOutcome,
    AdjudicationQueueItem,
    AdjudicationRecord,
    ReviewerPair,
    adjudication_reasons,
    load_adjudication_log,
    pair_locked_annotations,
    unresolved_queue_items,
    validate_queue_item_sources,
)
from floodguard.label_factory.annotation_rasterization import (
    CELL_LABEL_COLUMNS as REVIEWER_CELL_COLUMNS,
    GEOMETRY_PARTS_PAYLOAD_SCHEMA,
    QUERY_GRID_COLUMNS,
    AnnotationRasterizationDependencyError,
    canonical_geometry_parts_payload,
    rasterize_annotation_geometries,
)
from floodguard.label_factory.annotations import (
    AnnotationRecord,
    LabelClass,
    annotation_content_sha256,
    load_annotation_log,
)
from floodguard.label_factory.review_workflow import load_adjudication_queue_csv


CONSENSUS_RECEIPT_SCHEMA = "floodguard.consensus_builder_receipt.v1"
RASTER_LINEAGE_SCHEMA = "floodguard.reviewed_label_cells.v1"
REVIEWER_RASTER_SCHEMA = "floodguard.annotation_cell_raster.v1"
REDRAW_RASTER_SCHEMA = "floodguard.adjudicator_redraw_cell_raster.v1"
BUILDER_VERSION = "floodguard_consensus_builder_v1"
ALLOWED_LABEL_CODES = {0, 1, 2, 3, 4, 255}

FINAL_CELL_COLUMNS = (
    "event_id",
    "tile_id",
    "query_region_id",
    "cell_id",
    "row_index",
    "column_index",
    "label_code",
    "source_annotation_id",
    "source_adjudication_id",
    "source_support_annotation_ids",
    "selected_annotation_id",
    "cell_center_x",
    "cell_center_y",
    "crs",
    "grid_id",
    "grid_contract_sha256",
    "source_registry_sha256",
    "source_timestamp",
    "confidence",
    "assumptions",
)

REDRAW_CELL_COLUMNS = (
    "adjudication_id",
    "event_id",
    "tile_id",
    "query_region_id",
    "cell_id",
    "row_index",
    "column_index",
    "label_code",
    "cell_center_x",
    "cell_center_y",
    "crs",
    "grid_id",
    "grid_contract_sha256",
    "source_registry_sha256",
    "final_geometry_sha256",
    "eligible_for_query_model_training",
    "eligible_for_decision_layer",
    "eligible_for_fpps",
    "eligible_for_warning",
)


class ConsensusBuilderError(ValueError):
    """Raised when final cells cannot be derived without inventing truth."""


@dataclass(frozen=True, slots=True)
class ConsensusBuilderOutputs:
    """Immutable output paths produced by :func:`write_consensus_outputs`."""

    final_cells: Path
    raster_lineage: Path
    label_content: Path
    consensus_receipt: Path


@dataclass(frozen=True, slots=True)
class RedrawRasterOutputs:
    """Immutable adjudicator-redraw cell raster and its manifest."""

    cell_labels: Path
    manifest: Path


@dataclass(frozen=True, slots=True)
class ConsensusArtifacts:
    """In-memory, fully validated consensus artifacts."""

    final_cells: pd.DataFrame
    raster_lineage: dict[str, Any]
    label_content: dict[str, list[int]]
    consensus_receipt: dict[str, Any]


def write_adjudicator_redraw_outputs(
    *,
    adjudication_log_path: str | Path,
    query_manifest_path: str | Path,
    cell_output_path: str | Path,
    manifest_output_path: str | Path,
    rasterizer_version: str = BUILDER_VERSION,
) -> RedrawRasterOutputs:
    """Rasterize every locked redraw outcome onto its canonical query grid.

    Non-redraw outcomes are retained in the source log but do not emit cells.
    At least one locked redraw is required.  Geometry is independently checked
    against the query core and rasterized by cell centre using the same routine
    later used by consensus validation.
    """

    adjudication_log = _existing_file(adjudication_log_path, "adjudication log")
    query_path = _existing_file(query_manifest_path, "query manifest")
    cell_path = Path(cell_output_path)
    manifest_path = Path(manifest_output_path)
    if cell_path.suffix.lower() != ".csv":
        raise ConsensusBuilderError("Redraw cell output must end in .csv.")
    if manifest_path.suffix.lower() != ".json":
        raise ConsensusBuilderError("Redraw manifest output must end in .json.")
    _require_new_distinct_paths(
        {"cells": cell_path, "manifest": manifest_path},
        {"adjudication_log": adjudication_log, "query_manifest": query_path},
    )
    records = load_adjudication_log(adjudication_log)
    redraws = [
        record for record in records if record.outcome is AdjudicationOutcome.REDRAW
    ]
    if not redraws:
        raise ConsensusBuilderError(
            "Adjudication log contains no locked redraw outcome to rasterize."
        )
    if len({record.adjudication_id for record in redraws}) != len(redraws) or len(
        {record.query_region_id for record in redraws}
    ) != len(redraws):
        raise ConsensusBuilderError(
            "Redraw adjudications must have unique adjudication and query ids."
        )
    queries = _read_csv(query_path, label="query manifest")
    _require_columns(queries, QUERY_GRID_COLUMNS, "query manifest")
    if queries.empty or queries["query_region_id"].astype(str).duplicated().any():
        raise ConsensusBuilderError(
            "Query manifest must be non-empty with unique query_region_id values."
        )
    query_by_id = {
        str(row["query_region_id"]): row
        for row in queries.fillna("").to_dict("records")
    }
    rows: list[dict[str, Any]] = []
    for record in sorted(redraws, key=lambda item: item.adjudication_id):
        query = query_by_id.get(record.query_region_id)
        if query is None:
            raise ConsensusBuilderError(
                f"No canonical query exists for redraw {record.adjudication_id}."
            )
        if (str(query["event_id"]), str(query["tile_id"])) != (
            record.event_id,
            record.tile_id,
        ):
            raise ConsensusBuilderError(
                f"Redraw {record.adjudication_id} event/tile lineage mismatch."
            )
        _sha256(query["grid_contract_sha256"], "redraw grid hash")
        _sha256(query["source_registry_sha256"], "redraw source registry hash")
        _require_projected_crs(query["crs"])
        for field, expected in {
            "eligible_for_query_model_training": False,
            "eligible_for_decision_layer": False,
            "eligible_for_fpps": False,
            "eligible_for_warning": False,
        }.items():
            if _strict_bool(query[field], field) is not expected:
                raise ConsensusBuilderError(
                    f"Redraw query {record.query_region_id} has unsafe {field}."
                )
        rows.extend(_rasterize_redraw_geometry(record, query))
    cells = pd.DataFrame(rows, columns=REDRAW_CELL_COLUMNS).sort_values(
        ["query_region_id", "cell_id"], kind="stable"
    ).reset_index(drop=True)
    cell_bytes = _frame_csv_bytes(cells)
    cell_hash = hashlib.sha256(cell_bytes).hexdigest()
    payload = {
        "artifact_schema": REDRAW_RASTER_SCHEMA,
        "rasterizer_version": _required_text(
            rasterizer_version, "rasterizer_version"
        ),
        "adjudication_ids": sorted(record.adjudication_id for record in redraws),
        "source_adjudication_geometry_sha256": {
            record.adjudication_id: _canonical_json_sha256(record.final_geometry)
            for record in sorted(redraws, key=lambda item: item.adjudication_id)
        },
        "source_adjudication_log_sha256": _file_sha256(adjudication_log),
        "grid_contract_sha256_by_query": {
            record.query_region_id: str(
                query_by_id[record.query_region_id]["grid_contract_sha256"]
            ).lower()
            for record in sorted(redraws, key=lambda item: item.query_region_id)
        },
        "source_registry_sha256_by_query": {
            record.query_region_id: str(
                query_by_id[record.query_region_id]["source_registry_sha256"]
            ).lower()
            for record in sorted(redraws, key=lambda item: item.query_region_id)
        },
        "query_manifest_rows_sha256": _frame_sha256(queries),
        "cell_labels_file": cell_path.name,
        "cell_labels_sha256": cell_hash,
        "cell_count": len(cells),
        "eligible_for_query_model_training": False,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
        "assumptions": (
            "Deterministic cell-centre rasterization of locked adjudicator redraw "
            "geometry; cells outside explicit geometry remain unreviewed 255."
        ),
    }
    payloads = {
        cell_path: cell_bytes,
        manifest_path: _pretty_json_bytes(payload),
    }
    for path in payloads:
        path.parent.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    try:
        for path, data in payloads.items():
            with path.open("xb") as handle:
                handle.write(data)
            created.append(path)
    except Exception:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise
    return RedrawRasterOutputs(cell_labels=cell_path, manifest=manifest_path)


def write_consensus_outputs(
    *,
    annotation_log_path: str | Path,
    reviewer_a_id: str,
    reviewer_b_id: str,
    reviewer_a_cells_path: str | Path,
    reviewer_a_manifest_path: str | Path,
    reviewer_b_cells_path: str | Path,
    reviewer_b_manifest_path: str | Path,
    adjudication_queue_path: str | Path,
    adjudication_log_path: str | Path,
    query_manifest_path: str | Path,
    final_cells_path: str | Path,
    raster_lineage_path: str | Path,
    label_content_path: str | Path,
    consensus_receipt_path: str | Path,
    redraw_cells_path: str | Path | None = None,
    redraw_manifest_path: str | Path | None = None,
    builder_version: str = BUILDER_VERSION,
) -> ConsensusBuilderOutputs:
    """Validate source ownership and write one immutable consensus package.

    The four outputs are created only after every input has passed validation.
    Existing output files are never overwritten.
    """

    source_paths = {
        "annotation_log": _existing_file(annotation_log_path, "annotation log"),
        "reviewer_a_cells": _existing_file(reviewer_a_cells_path, "reviewer A cells"),
        "reviewer_a_manifest": _existing_file(
            reviewer_a_manifest_path, "reviewer A raster manifest"
        ),
        "reviewer_b_cells": _existing_file(reviewer_b_cells_path, "reviewer B cells"),
        "reviewer_b_manifest": _existing_file(
            reviewer_b_manifest_path, "reviewer B raster manifest"
        ),
        "adjudication_queue": _existing_file(
            adjudication_queue_path, "adjudication queue"
        ),
        "query_manifest": _existing_file(query_manifest_path, "query manifest"),
    }
    queue_items = load_adjudication_queue_csv(source_paths["adjudication_queue"])
    adjudication_log = Path(adjudication_log_path)
    if not adjudication_log.is_file() and queue_items:
        raise ConsensusBuilderError(
            "adjudication log is required when the adjudication queue is non-empty."
        )
    source_paths["adjudication_log"] = adjudication_log
    if (redraw_cells_path is None) != (redraw_manifest_path is None):
        raise ConsensusBuilderError(
            "redraw_cells_path and redraw_manifest_path must be supplied together."
        )
    if redraw_cells_path is not None and redraw_manifest_path is not None:
        source_paths["redraw_cells"] = _existing_file(redraw_cells_path, "redraw cells")
        source_paths["redraw_manifest"] = _existing_file(
            redraw_manifest_path, "redraw raster manifest"
        )

    targets = {
        "final_cells": Path(final_cells_path),
        "raster_lineage": Path(raster_lineage_path),
        "label_content": Path(label_content_path),
        "consensus_receipt": Path(consensus_receipt_path),
    }
    _require_new_distinct_paths(targets, source_paths)
    if targets["final_cells"].suffix.lower() != ".csv":
        raise ConsensusBuilderError("final_cells_path must end in .csv.")
    for name in ("raster_lineage", "label_content", "consensus_receipt"):
        if targets[name].suffix.lower() != ".json":
            raise ConsensusBuilderError(f"{name}_path must end in .json.")

    annotations = load_annotation_log(source_paths["annotation_log"])
    adjudications = (
        load_adjudication_log(source_paths["adjudication_log"])
        if source_paths["adjudication_log"].is_file()
        else []
    )
    queries = _read_csv(source_paths["query_manifest"], label="query manifest")
    reviewer_a_cells = _read_csv(
        source_paths["reviewer_a_cells"], label="reviewer A cells", strings=True
    )
    reviewer_b_cells = _read_csv(
        source_paths["reviewer_b_cells"], label="reviewer B cells", strings=True
    )
    reviewer_a_manifest = _read_json_object(
        source_paths["reviewer_a_manifest"], "reviewer A raster manifest"
    )
    reviewer_b_manifest = _read_json_object(
        source_paths["reviewer_b_manifest"], "reviewer B raster manifest"
    )
    redraw_cells = None
    redraw_manifest = None
    if "redraw_cells" in source_paths:
        redraw_cells = _read_csv(
            source_paths["redraw_cells"], label="redraw cells", strings=True
        )
        redraw_manifest = _read_json_object(
            source_paths["redraw_manifest"], "redraw raster manifest"
        )

    source_hashes = {
        name: (
            _file_sha256(path)
            if path.is_file()
            else hashlib.sha256(b"").hexdigest()
        )
        for name, path in sorted(source_paths.items())
    }
    artifacts = build_consensus_artifacts(
        annotation_records=annotations,
        reviewer_a_id=reviewer_a_id,
        reviewer_b_id=reviewer_b_id,
        reviewer_a_cells=reviewer_a_cells,
        reviewer_a_manifest=reviewer_a_manifest,
        reviewer_a_cell_name=source_paths["reviewer_a_cells"].name,
        reviewer_a_cell_sha256=source_hashes["reviewer_a_cells"],
        reviewer_b_cells=reviewer_b_cells,
        reviewer_b_manifest=reviewer_b_manifest,
        reviewer_b_cell_name=source_paths["reviewer_b_cells"].name,
        reviewer_b_cell_sha256=source_hashes["reviewer_b_cells"],
        queue_items=queue_items,
        adjudications=adjudications,
        query_manifest=queries,
        output_raster_name="final_cells",
        source_artifact_sha256=source_hashes,
        redraw_cells=redraw_cells,
        redraw_manifest=redraw_manifest,
        redraw_cell_name=(
            source_paths["redraw_cells"].name if "redraw_cells" in source_paths else None
        ),
        redraw_cell_sha256=source_hashes.get("redraw_cells"),
        builder_version=builder_version,
    )

    cell_bytes = _frame_csv_bytes(artifacts.final_cells)
    declared = artifacts.raster_lineage["rasters"]["final_cells"]["sha256"]
    if hashlib.sha256(cell_bytes).hexdigest() != declared:
        raise ConsensusBuilderError("Internal final-cell serialization hash mismatch.")
    payloads = {
        "final_cells": cell_bytes,
        "raster_lineage": _pretty_json_bytes(artifacts.raster_lineage),
        "label_content": _pretty_json_bytes(artifacts.label_content),
        "consensus_receipt": _pretty_json_bytes(artifacts.consensus_receipt),
    }
    for path in targets.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    try:
        for name, path in targets.items():
            with path.open("xb") as handle:
                handle.write(payloads[name])
            created.append(path)
    except Exception:
        # These paths were verified absent before the write and were created by
        # this invocation.  Roll back a partial four-artifact package so it can
        # never be mistaken for a complete immutable consensus release.
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise
    return ConsensusBuilderOutputs(
        final_cells=targets["final_cells"],
        raster_lineage=targets["raster_lineage"],
        label_content=targets["label_content"],
        consensus_receipt=targets["consensus_receipt"],
    )


def build_consensus_artifacts(
    *,
    annotation_records: Sequence[AnnotationRecord],
    reviewer_a_id: str,
    reviewer_b_id: str,
    reviewer_a_cells: pd.DataFrame,
    reviewer_a_manifest: Mapping[str, Any],
    reviewer_a_cell_name: str,
    reviewer_a_cell_sha256: str,
    reviewer_b_cells: pd.DataFrame,
    reviewer_b_manifest: Mapping[str, Any],
    reviewer_b_cell_name: str,
    reviewer_b_cell_sha256: str,
    queue_items: Sequence[AdjudicationQueueItem],
    adjudications: Sequence[AdjudicationRecord],
    query_manifest: pd.DataFrame,
    output_raster_name: str,
    source_artifact_sha256: Mapping[str, str],
    redraw_cells: pd.DataFrame | None = None,
    redraw_manifest: Mapping[str, Any] | None = None,
    redraw_cell_name: str | None = None,
    redraw_cell_sha256: str | None = None,
    builder_version: str = BUILDER_VERSION,
) -> ConsensusArtifacts:
    """Return final cells and the exact release-lineage contract."""

    version = _required_text(builder_version, "builder_version")
    raster_name = _required_text(output_raster_name, "output_raster_name")
    if Path(raster_name).name != raster_name or any(
        separator in raster_name for separator in ("/", "\\")
    ):
        raise ConsensusBuilderError("output_raster_name must be a stable logical name.")
    if not annotation_records:
        raise ConsensusBuilderError("The locked annotation log contains no records.")
    pairs = pair_locked_annotations(
        annotation_records,
        reviewer_a_id=reviewer_a_id,
        reviewer_b_id=reviewer_b_id,
    )
    if not pairs:
        raise ConsensusBuilderError("No latest locked reviewer pairs were found.")
    pair_by_key = {(pair.event_id, pair.query_region_id): pair for pair in pairs}
    if len(pair_by_key) != len(pairs):
        raise ConsensusBuilderError("Reviewer pair event/query ids must be unique.")
    query_by_id, grid_hash = _validate_query_manifest(query_manifest, pairs)

    a_records = tuple(pair.reviewer_a for pair in pairs)
    b_records = tuple(pair.reviewer_b for pair in pairs)
    trusted_a = _validate_reviewer_raster(
        label="reviewer A",
        records=a_records,
        expected_reviewer_id=reviewer_a_id,
        supplied_cells=reviewer_a_cells,
        manifest=reviewer_a_manifest,
        cell_name=reviewer_a_cell_name,
        cell_sha256=reviewer_a_cell_sha256,
        query_manifest=query_manifest,
    )
    trusted_b = _validate_reviewer_raster(
        label="reviewer B",
        records=b_records,
        expected_reviewer_id=reviewer_b_id,
        supplied_cells=reviewer_b_cells,
        manifest=reviewer_b_manifest,
        cell_name=reviewer_b_cell_name,
        cell_sha256=reviewer_b_cell_sha256,
        query_manifest=query_manifest,
    )
    queue_by_query, resolution_by_query = _validate_queue_and_resolutions(
        pairs, queue_items, adjudications
    )
    redraw_by_query = _validate_redraw_raster(
        redraw_cells=redraw_cells,
        redraw_manifest=redraw_manifest,
        redraw_cell_name=redraw_cell_name,
        redraw_cell_sha256=redraw_cell_sha256,
        adjudications=adjudications,
        query_manifest=query_manifest,
        query_by_id=query_by_id,
    )

    a_by_query = _cells_by_query(trusted_a)
    b_by_query = _cells_by_query(trusted_b)
    final_rows: list[dict[str, Any]] = []
    direct_receipts: list[dict[str, Any]] = []
    non_geometry_receipts: list[dict[str, Any]] = []
    geometry_receipts: list[dict[str, Any]] = []

    for pair in sorted(pairs, key=lambda item: (item.event_id, item.query_region_id)):
        query_id = pair.query_region_id
        query = query_by_id[query_id]
        cells_a = a_by_query[query_id]
        cells_b = b_by_query[query_id]
        if [row["cell_id"] for row in cells_a] != [row["cell_id"] for row in cells_b]:
            raise ConsensusBuilderError(f"Reviewer cell ids differ for {query_id}.")
        resolution = resolution_by_query.get((pair.event_id, query_id))
        if resolution is None:
            if (pair.event_id, query_id) in queue_by_query:
                raise ConsensusBuilderError(f"Query {query_id} has an unresolved queue item.")
            labels_a = [int(row["label_code"]) for row in cells_a]
            labels_b = [int(row["label_code"]) for row in cells_b]
            if labels_a != labels_b:
                raise ConsensusBuilderError(
                    f"Non-adjudicated query {query_id} has reviewer cell disagreement."
                )
            rows = _finalize_source_cells(
                cells_a,
                pair=pair,
                query=query,
                source_annotation_id=pair.reviewer_a.annotation_id,
                source_adjudication_id="",
                support_annotation_ids=(
                    pair.reviewer_a.annotation_id,
                    pair.reviewer_b.annotation_id,
                ),
                selected_annotation_id=pair.reviewer_a.annotation_id,
                confidence="double_review_exact_cell_agreement",
                assumptions=(
                    "Reviewer A is the deterministic byte carrier after exact A/B "
                    "cell agreement; both locked annotation ids are retained as support."
                ),
            )
            final_rows.extend(rows)
            direct_receipts.append(
                _direct_query_receipt(pair, rows)
            )
            continue

        outcome = resolution.outcome
        rows: list[dict[str, Any]] = []
        if outcome is AdjudicationOutcome.REJECT:
            non_geometry_receipts.append(
                _outcome_receipt(resolution, [], rule="query_omitted")
            )
            continue
        if outcome is AdjudicationOutcome.ACCEPT_A:
            selected_cells = cells_a
            selected_id = pair.reviewer_a.annotation_id
            rule = "selected_reviewer_a_exact_cells"
        elif outcome is AdjudicationOutcome.ACCEPT_B:
            selected_cells = cells_b
            selected_id = pair.reviewer_b.annotation_id
            rule = "selected_reviewer_b_exact_cells"
        elif outcome is AdjudicationOutcome.REDRAW:
            selected_cells = redraw_by_query.get(query_id)
            selected_id = ""
            rule = "adjudicator_geometry_cell_center_rasterization"
            if selected_cells is None:
                raise ConsensusBuilderError(
                    f"Redraw adjudication {resolution.adjudication_id} lacks redraw cells."
                )
        else:
            target = (
                int(LabelClass.UNCERTAIN_WATER_CHANGE)
                if outcome is AdjudicationOutcome.UNCERTAIN
                else int(LabelClass.UNOBSERVABLE_OR_ARTIFACT)
            )
            selected_cells = []
            for cell_a, cell_b in zip(cells_a, cells_b, strict=True):
                copied = dict(cell_a)
                copied["label_code"] = (
                    255
                    if 255 in {int(cell_a["label_code"]), int(cell_b["label_code"])}
                    else target
                )
                selected_cells.append(copied)
            selected_id = ""
            rule = "class_override_with_a_b_reviewed_support_intersection"

        rows = _finalize_source_cells(
            selected_cells,
            pair=pair,
            query=query,
            source_annotation_id="",
            source_adjudication_id=resolution.adjudication_id,
            support_annotation_ids=(
                pair.reviewer_a.annotation_id,
                pair.reviewer_b.annotation_id,
            ),
            selected_annotation_id=selected_id,
            confidence="locked_human_adjudication",
            assumptions=(
                f"Outcome={outcome.value}; rule={rule}; explicitly unreviewed source "
                "cells remain label_code=255."
            ),
        )
        if not any(int(row["label_code"]) != 255 for row in rows):
            raise ConsensusBuilderError(
                f"Non-rejected adjudication {resolution.adjudication_id} has no "
                "reviewed source-supported cell."
            )
        final_rows.extend(rows)
        if outcome in {
            AdjudicationOutcome.ACCEPT_A,
            AdjudicationOutcome.ACCEPT_B,
            AdjudicationOutcome.REDRAW,
        }:
            geometry_receipts.append(
                _geometry_query_receipt(resolution, rows, raster_name)
            )
        else:
            non_geometry_receipts.append(_outcome_receipt(resolution, rows, rule=rule))

    final = pd.DataFrame(final_rows, columns=FINAL_CELL_COLUMNS)
    if final.empty:
        raise ConsensusBuilderError("All reviewed queries were rejected; no labelset can be built.")
    final = final.sort_values(["query_region_id", "cell_id"], kind="stable").reset_index(
        drop=True
    )
    if final.duplicated(["query_region_id", "cell_id"]).any():
        raise ConsensusBuilderError("Final consensus contains duplicate query/cell ids.")
    cell_bytes = _frame_csv_bytes(final)
    cell_sha256 = hashlib.sha256(cell_bytes).hexdigest()
    labels = final["label_code"].astype(int)
    class_counts = {
        str(code): int(count)
        for code, count in labels.value_counts().sort_index().items()
    }
    label_content = {
        str(query_id): [int(value) for value in rows["label_code"]]
        for query_id, rows in final.groupby("query_region_id", sort=True)
    }
    geometry_ids = sorted(
        record.adjudication_id
        for record in adjudications
        if record.outcome
        in {
            AdjudicationOutcome.ACCEPT_A,
            AdjudicationOutcome.ACCEPT_B,
            AdjudicationOutcome.REDRAW,
        }
    )
    receipt_without_hash: dict[str, Any] = {
        "artifact_schema": CONSENSUS_RECEIPT_SCHEMA,
        "builder_version": version,
        "grid_contract_sha256": grid_hash,
        "source_adjudication_ids": geometry_ids,
        "output_raster_sha256_by_name": {raster_name: cell_sha256},
        "query_receipts": sorted(
            geometry_receipts, key=lambda row: str(row["adjudication_id"])
        ),
        "direct_consensus_receipts": sorted(
            direct_receipts, key=lambda row: str(row["query_region_id"])
        ),
        "non_geometry_adjudication_receipts": sorted(
            non_geometry_receipts, key=lambda row: str(row["adjudication_id"])
        ),
        "source_annotation_content_sha256": {
            record.annotation_id: annotation_content_sha256(record)
            for pair in sorted(pairs, key=lambda item: item.query_region_id)
            for record in (pair.reviewer_a, pair.reviewer_b)
        },
        "source_adjudication_content_sha256": {
            record.adjudication_id: _canonical_json_sha256(record.to_dict())
            for record in sorted(adjudications, key=lambda item: item.adjudication_id)
        },
        "input_artifact_sha256": {
            str(name): _sha256(value, f"input artifact {name}")
            for name, value in sorted(source_artifact_sha256.items())
        },
        "query_manifest_rows_sha256": _frame_sha256(query_manifest),
        "query_lineage_by_query": {
            pair.query_region_id: {
                "event_id": pair.event_id,
                "tile_id": pair.tile_id,
                "grid_contract_sha256": str(
                    query_by_id[pair.query_region_id]["grid_contract_sha256"]
                ),
                "source_registry_sha256": str(
                    query_by_id[pair.query_region_id]["source_registry_sha256"]
                ),
            }
            for pair in sorted(pairs, key=lambda item: item.query_region_id)
        },
        "final_cell_count": len(final),
        "class_counts": class_counts,
        "eligible_for_query_model_training": False,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
        "assumptions": (
            "Deterministic cell-centre consensus from two locked blinded reviews and "
            "their exact locked adjudication outcomes; no human decision was inferred."
        ),
    }
    receipt = {
        **receipt_without_hash,
        "receipt_sha256": _canonical_json_sha256(receipt_without_hash),
    }
    lineage: dict[str, Any] = {
        "artifact_schema": RASTER_LINEAGE_SCHEMA,
        "grid_contract_sha256": grid_hash,
        "rasterizer_version": version,
        "source_annotation_ids": sorted(
            record.annotation_id
            for pair in pairs
            for record in (pair.reviewer_a, pair.reviewer_b)
        ),
        "source_adjudication_ids": sorted(
            record.adjudication_id for record in adjudications
        ),
        "source_registry_sha256_by_query": {
            pair.query_region_id: str(
                query_by_id[pair.query_region_id]["source_registry_sha256"]
            )
            for pair in sorted(pairs, key=lambda item: item.query_region_id)
        },
        "input_artifact_sha256": dict(receipt["input_artifact_sha256"]),
        "eligible_for_query_model_training": False,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
        "rasters": {
            raster_name: {
                "format": "canonical_cell_csv_v1",
                "sha256": cell_sha256,
                "cell_count": len(final),
                "class_counts": class_counts,
            }
        },
    }
    # Every release path, including direct agreement and reject-only branches,
    # is bound by the same mandatory receipt contract.
    lineage["consensus_builder_receipt"] = receipt
    return ConsensusArtifacts(
        final_cells=final,
        raster_lineage=lineage,
        label_content=label_content,
        consensus_receipt=receipt,
    )


def _validate_query_manifest(
    frame: pd.DataFrame,
    pairs: Sequence[ReviewerPair],
) -> tuple[dict[str, dict[str, Any]], str]:
    _require_columns(frame, QUERY_GRID_COLUMNS, "query manifest")
    if frame.empty or frame["query_region_id"].astype(str).duplicated().any():
        raise ConsensusBuilderError(
            "Query manifest must be non-empty with unique query_region_id values."
        )
    query_by_id = {
        str(row["query_region_id"]).strip(): row
        for row in frame.fillna("").to_dict("records")
    }
    expected_queries = {pair.query_region_id for pair in pairs}
    missing = sorted(expected_queries - set(query_by_id))
    if missing:
        raise ConsensusBuilderError(
            f"Query manifest does not cover reviewed pairs: {missing[:5]!r}."
        )
    relevant_grid_hashes: set[str] = set()
    for pair in pairs:
        row = query_by_id[pair.query_region_id]
        if (str(row["event_id"]), str(row["tile_id"])) != (
            pair.event_id,
            pair.tile_id,
        ):
            raise ConsensusBuilderError(
                f"Query lineage does not match reviewer pair {pair.query_region_id}."
            )
        _positive_integer(row["query_size_pixels"], "query_size_pixels")
        _require_projected_crs(row["crs"])
        relevant_grid_hashes.add(_sha256(row["grid_contract_sha256"], "grid hash"))
        _sha256(row["source_registry_sha256"], "source registry hash")
        for field, expected in {
            "eligible_for_agreement": True,
            "eligible_for_query_model_training": False,
            "eligible_for_decision_layer": False,
            "eligible_for_fpps": False,
            "eligible_for_warning": False,
        }.items():
            if _strict_bool(row[field], field) is not expected:
                raise ConsensusBuilderError(
                    f"Query {pair.query_region_id} has unsafe {field}."
                )
        _required_text(row["source_timestamp"], "source_timestamp")
        _required_text(row["assumptions"], "assumptions")
    if len(relevant_grid_hashes) != 1:
        raise ConsensusBuilderError("One consensus release may use only one canonical grid.")
    return query_by_id, next(iter(relevant_grid_hashes))


def _validate_reviewer_raster(
    *,
    label: str,
    records: Sequence[AnnotationRecord],
    expected_reviewer_id: str,
    supplied_cells: pd.DataFrame,
    manifest: Mapping[str, Any],
    cell_name: str,
    cell_sha256: str,
    query_manifest: pd.DataFrame,
) -> pd.DataFrame:
    if any(record.reviewer_id != expected_reviewer_id for record in records):
        raise ConsensusBuilderError(f"{label} source ownership is inconsistent.")
    expected_annotation_hashes = {
        record.annotation_id: annotation_content_sha256(record)
        for record in sorted(records, key=lambda item: item.annotation_id)
    }
    if not isinstance(manifest, Mapping) or manifest.get("artifact_schema") != REVIEWER_RASTER_SCHEMA:
        raise ConsensusBuilderError(
            f"{label} manifest must use artifact_schema={REVIEWER_RASTER_SCHEMA!r}."
        )
    if manifest.get("annotation_ids") != sorted(expected_annotation_hashes):
        raise ConsensusBuilderError(f"{label} manifest annotation ownership mismatch.")
    if manifest.get("source_annotation_content_sha256") != expected_annotation_hashes:
        raise ConsensusBuilderError(f"{label} manifest annotation hashes mismatch.")
    if manifest.get("cell_labels_file") != cell_name:
        raise ConsensusBuilderError(f"{label} manifest cell filename mismatch.")
    if _sha256(manifest.get("cell_labels_sha256"), f"{label} cell hash") != _sha256(
        cell_sha256, f"{label} observed cell hash"
    ):
        raise ConsensusBuilderError(f"{label} cell file hash mismatch.")
    if int(manifest.get("cell_count", -1)) != len(supplied_cells):
        raise ConsensusBuilderError(f"{label} manifest cell_count mismatch.")
    expected_grid = {
        str(row["query_region_id"]): str(row["grid_contract_sha256"]).lower()
        for row in query_manifest.fillna("").to_dict("records")
    }
    expected_registry = {
        str(row["query_region_id"]): str(row["source_registry_sha256"]).lower()
        for row in query_manifest.fillna("").to_dict("records")
    }
    if manifest.get("grid_contract_sha256_by_query") != expected_grid:
        raise ConsensusBuilderError(f"{label} manifest grid lineage mismatch.")
    if manifest.get("source_registry_sha256_by_query") != expected_registry:
        raise ConsensusBuilderError(f"{label} manifest source registry lineage mismatch.")
    if manifest.get("query_manifest_rows_sha256") != _frame_sha256(query_manifest):
        raise ConsensusBuilderError(f"{label} manifest query rows hash mismatch.")
    for field, expected in {
        "eligible_for_agreement": True,
        "eligible_for_query_model_training": False,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }.items():
        if manifest.get(field) is not expected:
            raise ConsensusBuilderError(f"{label} manifest has unsafe {field}.")

    parts = _locked_geometry_parts(records)
    try:
        recomputed = rasterize_annotation_geometries(records, query_manifest, parts)
    except AnnotationRasterizationDependencyError:
        raise
    except ValueError as exc:
        raise ConsensusBuilderError(
            f"Could not independently recompute {label} geometry cells: {exc}"
        ) from exc
    _require_exact_reviewer_cells(supplied_cells, recomputed, label=label)
    return recomputed.sort_values(["query_region_id", "cell_id"], kind="stable").reset_index(
        drop=True
    )


def _locked_geometry_parts(records: Sequence[AnnotationRecord]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for record in records:
        geometry = record.geometry
        if not isinstance(geometry, str) or not geometry.lstrip().startswith("{"):
            raise ConsensusBuilderError(
                f"Annotation {record.annotation_id} lacks a canonical locked geometry-parts payload."
            )
        try:
            payload = json.loads(geometry)
        except json.JSONDecodeError as exc:
            raise ConsensusBuilderError(
                f"Annotation {record.annotation_id} geometry payload is invalid JSON."
            ) from exc
        if not isinstance(payload, Mapping) or payload.get("schema") != GEOMETRY_PARTS_PAYLOAD_SCHEMA:
            raise ConsensusBuilderError(
                f"Annotation {record.annotation_id} uses an unsupported geometry payload."
            )
        parts = payload.get("parts")
        fill = payload.get("fill_unpainted_with_primary_class")
        if not isinstance(parts, list) or not parts or not isinstance(fill, bool):
            raise ConsensusBuilderError(
                f"Annotation {record.annotation_id} geometry payload is incomplete."
            )
        annotation_rows: list[dict[str, Any]] = []
        for part in parts:
            if not isinstance(part, Mapping):
                raise ConsensusBuilderError(
                    f"Annotation {record.annotation_id} has an invalid geometry part."
                )
            annotation_rows.append(
                {
                    "annotation_id": record.annotation_id,
                    "geometry_part_id": part.get("geometry_part_id"),
                    "class_code": part.get("class_code"),
                    "geometry_wkt": part.get("geometry_wkt"),
                    "fill_unpainted_with_primary_class": fill,
                }
            )
        part_frame = pd.DataFrame(annotation_rows)
        try:
            canonical = canonical_geometry_parts_payload(part_frame)
        except ValueError as exc:
            raise ConsensusBuilderError(
                f"Annotation {record.annotation_id} geometry payload is invalid: {exc}"
            ) from exc
        if canonical != geometry:
            raise ConsensusBuilderError(
                f"Annotation {record.annotation_id} geometry payload is not canonical."
            )
        rows.extend(annotation_rows)
    return pd.DataFrame(rows)


def _require_exact_reviewer_cells(
    supplied: pd.DataFrame,
    recomputed: pd.DataFrame,
    *,
    label: str,
) -> None:
    if tuple(supplied.columns) != tuple(REVIEWER_CELL_COLUMNS):
        raise ConsensusBuilderError(
            f"{label} cell CSV columns must exactly match the canonical raster schema."
        )
    if len(supplied) != len(recomputed):
        raise ConsensusBuilderError(f"{label} cell coverage differs from locked geometry.")
    supplied_sorted = supplied.sort_values(
        ["query_region_id", "cell_id"], kind="stable"
    ).reset_index(drop=True)
    expected_sorted = recomputed.sort_values(
        ["query_region_id", "cell_id"], kind="stable"
    ).reset_index(drop=True)
    for index, (observed, expected) in enumerate(
        zip(
            supplied_sorted.to_dict("records"),
            expected_sorted.to_dict("records"),
            strict=True,
        )
    ):
        for field in REVIEWER_CELL_COLUMNS:
            if field in {"row_index", "column_index", "label_code"}:
                equal = _integer(observed[field], field) == int(expected[field])
            elif field in {"cell_center_x", "cell_center_y"}:
                equal = math.isclose(
                    _finite(observed[field], field),
                    float(expected[field]),
                    rel_tol=1e-12,
                    abs_tol=1e-9,
                )
            elif field.startswith("eligible_for_"):
                equal = _strict_bool(observed[field], field) is bool(expected[field])
            else:
                equal = str(observed[field]) == str(expected[field])
            if not equal:
                raise ConsensusBuilderError(
                    f"{label} cell CSV is not the locked-geometry raster at row "
                    f"{index}, field {field}."
                )


def _validate_queue_and_resolutions(
    pairs: Sequence[ReviewerPair],
    queue_items: Sequence[AdjudicationQueueItem],
    adjudications: Sequence[AdjudicationRecord],
) -> tuple[
    dict[tuple[str, str], AdjudicationQueueItem],
    dict[tuple[str, str], AdjudicationRecord],
]:
    pair_by_key = {(pair.event_id, pair.query_region_id): pair for pair in pairs}
    expected_queue_keys = {
        key for key, pair in pair_by_key.items() if adjudication_reasons(pair)
    }
    queue_by_key: dict[tuple[str, str], AdjudicationQueueItem] = {}
    for item in queue_items:
        key = (item.event_id, item.query_region_id)
        pair = pair_by_key.get(key)
        if pair is None or key in queue_by_key:
            raise ConsensusBuilderError(
                f"Adjudication queue contains duplicate or unknown query {key}."
            )
        validate_queue_item_sources(item, pair)
        if set(item.reason_codes) != set(adjudication_reasons(pair)):
            raise ConsensusBuilderError(
                f"Adjudication queue reasons do not match locked pair {key}."
            )
        queue_by_key[key] = item
    if set(queue_by_key) != expected_queue_keys:
        raise ConsensusBuilderError(
            "Adjudication queue does not exactly cover protocol-triggering pairs; "
            f"missing={sorted(expected_queue_keys - set(queue_by_key))}, "
            f"extra={sorted(set(queue_by_key) - expected_queue_keys)}."
        )
    try:
        unresolved = unresolved_queue_items(queue_items, adjudications)
    except ValueError as exc:
        raise ConsensusBuilderError(f"Invalid adjudication lineage: {exc}") from exc
    if unresolved:
        raise ConsensusBuilderError(
            "All queue items must be resolved before consensus construction; open="
            + ", ".join(item.queue_id for item in unresolved)
        )
    resolution_by_key: dict[tuple[str, str], AdjudicationRecord] = {}
    for record in adjudications:
        key = (record.event_id, record.query_region_id)
        if key in resolution_by_key:
            raise ConsensusBuilderError(f"Query {key} was adjudicated more than once.")
        resolution_by_key[key] = record
    if set(resolution_by_key) != set(queue_by_key):
        raise ConsensusBuilderError("Adjudication log query coverage differs from the queue.")
    return queue_by_key, resolution_by_key


def _validate_redraw_raster(
    *,
    redraw_cells: pd.DataFrame | None,
    redraw_manifest: Mapping[str, Any] | None,
    redraw_cell_name: str | None,
    redraw_cell_sha256: str | None,
    adjudications: Sequence[AdjudicationRecord],
    query_manifest: pd.DataFrame,
    query_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    redraws = {
        record.query_region_id: record
        for record in adjudications
        if record.outcome is AdjudicationOutcome.REDRAW
    }
    inputs = (redraw_cells, redraw_manifest, redraw_cell_name, redraw_cell_sha256)
    if not redraws:
        if any(value is not None for value in inputs):
            raise ConsensusBuilderError(
                "Redraw raster inputs were supplied but no adjudication outcome is redraw."
            )
        return {}
    if any(value is None for value in inputs):
        raise ConsensusBuilderError(
            "Every redraw outcome requires redraw cells and its bound raster manifest."
        )
    assert redraw_cells is not None
    assert redraw_manifest is not None
    assert redraw_cell_name is not None
    assert redraw_cell_sha256 is not None
    if tuple(redraw_cells.columns) != REDRAW_CELL_COLUMNS:
        raise ConsensusBuilderError(
            "Redraw cell CSV columns must exactly match REDRAW_CELL_COLUMNS."
        )
    if not isinstance(redraw_manifest, Mapping) or redraw_manifest.get(
        "artifact_schema"
    ) != REDRAW_RASTER_SCHEMA:
        raise ConsensusBuilderError(
            f"Redraw manifest must use artifact_schema={REDRAW_RASTER_SCHEMA!r}."
        )
    expected_geometry_hashes = {
        record.adjudication_id: _canonical_json_sha256(record.final_geometry)
        for record in sorted(redraws.values(), key=lambda item: item.adjudication_id)
    }
    if redraw_manifest.get("adjudication_ids") != sorted(expected_geometry_hashes):
        raise ConsensusBuilderError("Redraw manifest adjudication ownership mismatch.")
    if redraw_manifest.get("source_adjudication_geometry_sha256") != expected_geometry_hashes:
        raise ConsensusBuilderError("Redraw manifest geometry hashes mismatch.")
    if redraw_manifest.get("cell_labels_file") != redraw_cell_name:
        raise ConsensusBuilderError("Redraw manifest cell filename mismatch.")
    if _sha256(redraw_manifest.get("cell_labels_sha256"), "redraw cell hash") != _sha256(
        redraw_cell_sha256, "observed redraw cell hash"
    ):
        raise ConsensusBuilderError("Redraw cell file hash mismatch.")
    if int(redraw_manifest.get("cell_count", -1)) != len(redraw_cells):
        raise ConsensusBuilderError("Redraw manifest cell_count mismatch.")
    expected_grid = {
        record.query_region_id: str(
            query_by_id[record.query_region_id]["grid_contract_sha256"]
        ).lower()
        for record in redraws.values()
    }
    expected_registry = {
        record.query_region_id: str(
            query_by_id[record.query_region_id]["source_registry_sha256"]
        ).lower()
        for record in redraws.values()
    }
    if redraw_manifest.get("grid_contract_sha256_by_query") != expected_grid:
        raise ConsensusBuilderError("Redraw manifest grid lineage mismatch.")
    if redraw_manifest.get("source_registry_sha256_by_query") != expected_registry:
        raise ConsensusBuilderError("Redraw manifest source registry lineage mismatch.")
    if redraw_manifest.get("query_manifest_rows_sha256") != _frame_sha256(query_manifest):
        raise ConsensusBuilderError("Redraw manifest query rows hash mismatch.")
    for field, expected in {
        "eligible_for_query_model_training": False,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }.items():
        if redraw_manifest.get(field) is not expected:
            raise ConsensusBuilderError(f"Redraw manifest has unsafe {field}.")

    expected_rows: list[dict[str, Any]] = []
    for record in redraws.values():
        expected_rows.extend(_rasterize_redraw_geometry(record, query_by_id[record.query_region_id]))
    expected = pd.DataFrame(expected_rows, columns=REDRAW_CELL_COLUMNS).sort_values(
        ["query_region_id", "cell_id"], kind="stable"
    ).reset_index(drop=True)
    supplied = redraw_cells.sort_values(
        ["query_region_id", "cell_id"], kind="stable"
    ).reset_index(drop=True)
    if len(supplied) != len(expected):
        raise ConsensusBuilderError("Redraw cell coverage differs from adjudication geometry.")
    for index, (observed, truth) in enumerate(
        zip(supplied.to_dict("records"), expected.to_dict("records"), strict=True)
    ):
        for field in REDRAW_CELL_COLUMNS:
            if field in {"row_index", "column_index", "label_code"}:
                equal = _integer(observed[field], field) == int(truth[field])
            elif field in {"cell_center_x", "cell_center_y"}:
                equal = math.isclose(
                    _finite(observed[field], field),
                    float(truth[field]),
                    rel_tol=1e-12,
                    abs_tol=1e-9,
                )
            elif field.startswith("eligible_for_"):
                equal = _strict_bool(observed[field], field) is bool(truth[field])
            else:
                equal = str(observed[field]) == str(truth[field])
            if not equal:
                raise ConsensusBuilderError(
                    f"Redraw cell raster is not the locked adjudication geometry at "
                    f"row {index}, field {field}."
                )
    return {
        query_id: rows
        for query_id, rows in _cells_by_query(expected).items()
    }


def _rasterize_redraw_geometry(
    record: AdjudicationRecord,
    query: Mapping[str, Any],
) -> list[dict[str, Any]]:
    try:
        from shapely import Point, box, wkt
    except (ImportError, ModuleNotFoundError) as exc:
        raise AnnotationRasterizationDependencyError(
            "Consensus redraw verification requires the optional geo dependency; "
            "install it with `uv sync --extra geo`."
        ) from exc
    geometry_text = record.final_geometry
    if not isinstance(geometry_text, str) or not geometry_text.strip():
        raise ConsensusBuilderError(
            f"Redraw {record.adjudication_id} has no locked final geometry."
        )
    size = _positive_integer(query["query_size_pixels"], "query_size_pixels")
    min_x = _finite(query["bbox_min_x"], "bbox_min_x")
    min_y = _finite(query["bbox_min_y"], "bbox_min_y")
    max_x = _finite(query["bbox_max_x"], "bbox_max_x")
    max_y = _finite(query["bbox_max_y"], "bbox_max_y")
    if min_x >= max_x or min_y >= max_y:
        raise ConsensusBuilderError("Redraw query bounds are invalid.")
    cell_width = (max_x - min_x) / size
    cell_height = (max_y - min_y) / size
    if not math.isclose(cell_width, cell_height, rel_tol=1e-9, abs_tol=1e-9):
        raise ConsensusBuilderError("Redraw cells must be square in a projected CRS.")
    query_polygon = box(min_x, min_y, max_x, max_y)
    parts: list[tuple[int, object]] = []
    fill_primary = False
    if geometry_text.lstrip().startswith("{"):
        try:
            payload = json.loads(geometry_text)
        except json.JSONDecodeError as exc:
            raise ConsensusBuilderError("Redraw geometry payload is invalid JSON.") from exc
        if not isinstance(payload, Mapping) or payload.get("schema") != GEOMETRY_PARTS_PAYLOAD_SCHEMA:
            raise ConsensusBuilderError("Redraw geometry payload schema is unsupported.")
        raw_parts = payload.get("parts")
        fill_primary = payload.get("fill_unpainted_with_primary_class")
        if not isinstance(raw_parts, list) or not raw_parts or not isinstance(fill_primary, bool):
            raise ConsensusBuilderError("Redraw geometry payload is incomplete.")
        validation_rows = pd.DataFrame(
            [
                {
                    "annotation_id": record.adjudication_id,
                    "geometry_part_id": part.get("geometry_part_id"),
                    "class_code": part.get("class_code"),
                    "geometry_wkt": part.get("geometry_wkt"),
                    "fill_unpainted_with_primary_class": fill_primary,
                }
                for part in raw_parts
                if isinstance(part, Mapping)
            ]
        )
        if len(validation_rows) != len(raw_parts):
            raise ConsensusBuilderError("Redraw geometry payload contains a non-object part.")
        try:
            canonical = canonical_geometry_parts_payload(validation_rows)
        except ValueError as exc:
            raise ConsensusBuilderError(f"Redraw geometry payload is invalid: {exc}") from exc
        if canonical != geometry_text:
            raise ConsensusBuilderError("Redraw geometry payload is not canonical.")
        for part in raw_parts:
            wkt_text = str(part["geometry_wkt"])
            if not wkt_text:
                continue
            parts.append(
                (
                    _label_code(part["class_code"], "redraw class_code", drawable=True),
                    _polygon(wkt.loads, wkt_text, query_polygon, "redraw geometry part"),
                )
            )
    else:
        assert record.final_primary_class is not None
        parts.append(
            (
                int(record.final_primary_class),
                _polygon(wkt.loads, geometry_text, query_polygon, "redraw final_geometry"),
            )
        )

    geometry_hash = _canonical_json_sha256(geometry_text)
    output: list[dict[str, Any]] = []
    for row_index in range(size):
        y = max_y - (row_index + 0.5) * cell_height
        for column_index in range(size):
            x = min_x + (column_index + 0.5) * cell_width
            point = Point(x, y)
            matches = {code for code, geometry in parts if geometry.covers(point)}
            if len(matches) > 1:
                raise ConsensusBuilderError(
                    f"Redraw geometry assigns multiple classes at cell {row_index}/{column_index}."
                )
            if matches:
                code = next(iter(matches))
            elif fill_primary:
                assert record.final_primary_class is not None
                code = int(record.final_primary_class)
            else:
                code = 255
            output.append(
                {
                    "adjudication_id": record.adjudication_id,
                    "event_id": record.event_id,
                    "tile_id": record.tile_id,
                    "query_region_id": record.query_region_id,
                    "cell_id": f"{record.query_region_id}_R{row_index:04d}_C{column_index:04d}",
                    "row_index": row_index,
                    "column_index": column_index,
                    "label_code": code,
                    "cell_center_x": x,
                    "cell_center_y": y,
                    "crs": str(query["crs"]),
                    "grid_id": str(query["grid_id"]),
                    "grid_contract_sha256": str(query["grid_contract_sha256"]),
                    "source_registry_sha256": str(query["source_registry_sha256"]),
                    "final_geometry_sha256": geometry_hash,
                    "eligible_for_query_model_training": False,
                    "eligible_for_decision_layer": False,
                    "eligible_for_fpps": False,
                    "eligible_for_warning": False,
                }
            )
    return output


def _polygon(loader: Any, value: str, query_polygon: Any, label: str) -> Any:
    try:
        geometry = loader(value)
    except Exception as exc:
        raise ConsensusBuilderError(f"{label} is not valid WKT.") from exc
    if (
        geometry.is_empty
        or geometry.geom_type not in {"Polygon", "MultiPolygon"}
        or not geometry.is_valid
    ):
        raise ConsensusBuilderError(f"{label} must be a valid non-empty polygon.")
    if not query_polygon.covers(geometry):
        raise ConsensusBuilderError(f"{label} extends outside the canonical query core.")
    return geometry


def _cells_by_query(frame: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
    return {
        str(query_id): rows.sort_values("cell_id", kind="stable").to_dict("records")
        for query_id, rows in frame.groupby("query_region_id", sort=True)
    }


def _finalize_source_cells(
    source_cells: Sequence[Mapping[str, Any]],
    *,
    pair: ReviewerPair,
    query: Mapping[str, Any],
    source_annotation_id: str,
    source_adjudication_id: str,
    support_annotation_ids: Sequence[str],
    selected_annotation_id: str,
    confidence: str,
    assumptions: str,
) -> list[dict[str, Any]]:
    if bool(source_annotation_id) == bool(source_adjudication_id):
        raise ConsensusBuilderError(
            "Each consensus query must have exactly one annotation or adjudication owner."
        )
    output: list[dict[str, Any]] = []
    for row in source_cells:
        label = _label_code(row["label_code"], "label_code")
        output.append(
            {
                "event_id": pair.event_id,
                "tile_id": pair.tile_id,
                "query_region_id": pair.query_region_id,
                "cell_id": str(row["cell_id"]),
                "row_index": _integer(row["row_index"], "row_index"),
                "column_index": _integer(row["column_index"], "column_index"),
                "label_code": label,
                "source_annotation_id": source_annotation_id,
                "source_adjudication_id": source_adjudication_id,
                "source_support_annotation_ids": ";".join(sorted(support_annotation_ids)),
                "selected_annotation_id": selected_annotation_id,
                "cell_center_x": _finite(row["cell_center_x"], "cell_center_x"),
                "cell_center_y": _finite(row["cell_center_y"], "cell_center_y"),
                "crs": str(query["crs"]),
                "grid_id": str(query["grid_id"]),
                "grid_contract_sha256": str(query["grid_contract_sha256"]),
                "source_registry_sha256": str(query["source_registry_sha256"]),
                "source_timestamp": str(query["source_timestamp"]),
                "confidence": confidence,
                "assumptions": f"{query['assumptions']} {assumptions}",
            }
        )
    return output


def _direct_query_receipt(pair: ReviewerPair, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: str(row["cell_id"]))
    return {
        "query_region_id": pair.query_region_id,
        "reviewer_a_annotation_id": pair.reviewer_a.annotation_id,
        "reviewer_b_annotation_id": pair.reviewer_b.annotation_id,
        "reviewer_a_sha256": annotation_content_sha256(pair.reviewer_a),
        "reviewer_b_sha256": annotation_content_sha256(pair.reviewer_b),
        "cell_ids_sha256": _canonical_json_sha256(
            [str(row["cell_id"]) for row in ordered]
        ),
        "labeled_cells_sha256": _canonical_json_sha256(
            [
                {"cell_id": str(row["cell_id"]), "label_code": int(row["label_code"])}
                for row in ordered
            ]
        ),
        "reviewer_cells_exactly_equal": True,
    }


def _geometry_query_receipt(
    record: AdjudicationRecord,
    rows: Sequence[Mapping[str, Any]],
    raster_name: str,
) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: str(row["cell_id"]))
    return {
        "adjudication_id": record.adjudication_id,
        "query_region_id": record.query_region_id,
        "outcome": record.outcome.value,
        "final_geometry_sha256": _canonical_json_sha256(record.final_geometry),
        "cell_ids_sha256": _canonical_json_sha256(
            [str(row["cell_id"]) for row in ordered]
        ),
        "labeled_cells_sha256": _canonical_json_sha256(
            [
                {"cell_id": str(row["cell_id"]), "label_code": int(row["label_code"])}
                for row in ordered
            ]
        ),
        "output_raster_name": raster_name,
        "verified_against_final_geometry": True,
    }


def _outcome_receipt(
    record: AdjudicationRecord,
    rows: Sequence[Mapping[str, Any]],
    *,
    rule: str,
) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: str(row["cell_id"]))
    return {
        "adjudication_id": record.adjudication_id,
        "query_region_id": record.query_region_id,
        "outcome": record.outcome.value,
        "derivation_rule": rule,
        "query_omitted": record.outcome is AdjudicationOutcome.REJECT,
        "cell_ids_sha256": _canonical_json_sha256(
            [str(row["cell_id"]) for row in ordered]
        ),
        "labeled_cells_sha256": _canonical_json_sha256(
            [
                {"cell_id": str(row["cell_id"]), "label_code": int(row["label_code"])}
                for row in ordered
            ]
        ),
    }


def _read_csv(path: Path, *, label: str, strings: bool = False) -> pd.DataFrame:
    try:
        return pd.read_csv(
            path,
            dtype=str if strings else None,
            keep_default_na=not strings,
        ).fillna("")
    except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise ConsensusBuilderError(f"Could not read {label}: {path}") from exc


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConsensusBuilderError(f"Could not read {label}: {path}") from exc
    if not isinstance(payload, dict):
        raise ConsensusBuilderError(f"{label} must be a JSON object.")
    return payload


def _existing_file(value: str | Path, label: str) -> Path:
    path = Path(value)
    if not path.is_file():
        raise ConsensusBuilderError(f"{label} does not exist: {path}")
    return path


def _require_new_distinct_paths(
    targets: Mapping[str, Path],
    sources: Mapping[str, Path],
) -> None:
    resolved_targets = [path.resolve() for path in targets.values()]
    if len(set(resolved_targets)) != len(resolved_targets):
        raise ConsensusBuilderError("Consensus output paths must be distinct.")
    source_set = {path.resolve() for path in sources.values()}
    if source_set.intersection(resolved_targets):
        raise ConsensusBuilderError("Consensus outputs may not overwrite source artifacts.")
    existing = [str(path) for path in targets.values() if path.exists()]
    if existing:
        raise ConsensusBuilderError(
            "Consensus outputs are immutable and already exist: " + ", ".join(existing)
        )


def _require_columns(frame: pd.DataFrame, required: Sequence[str], label: str) -> None:
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise ConsensusBuilderError(f"{label} is missing columns: {', '.join(missing)}")


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConsensusBuilderError(f"{label} must be a non-blank string.")
    return value.strip()


def _strict_bool(value: Any, label: str) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1"}:
        return True
    if text in {"false", "0"}:
        return False
    raise ConsensusBuilderError(f"{label} must be an explicit boolean.")


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise ConsensusBuilderError(f"{label} must be an integer.")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ConsensusBuilderError(f"{label} must be an integer.") from exc
    try:
        if float(value) != number:
            raise ConsensusBuilderError(f"{label} must be an integer.")
    except (TypeError, ValueError) as exc:
        raise ConsensusBuilderError(f"{label} must be an integer.") from exc
    return number


def _positive_integer(value: Any, label: str) -> int:
    number = _integer(value, label)
    if number <= 0:
        raise ConsensusBuilderError(f"{label} must be positive.")
    return number


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ConsensusBuilderError(f"{label} must be finite numeric data.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ConsensusBuilderError(f"{label} must be finite numeric data.") from exc
    if not math.isfinite(number):
        raise ConsensusBuilderError(f"{label} must be finite numeric data.")
    return number


def _label_code(value: Any, label: str, *, drawable: bool = False) -> int:
    code = _integer(value, label)
    allowed = ALLOWED_LABEL_CODES - ({255} if drawable else set())
    if code not in allowed:
        raise ConsensusBuilderError(f"{label} is not in the canonical label taxonomy.")
    return code


def _require_projected_crs(value: Any) -> str:
    text = _required_text(str(value), "crs").upper()
    if text in {"EPSG:4326", "CRS84", "OGC:CRS84"}:
        raise ConsensusBuilderError("Consensus cells require a projected canonical CRS.")
    return text


def _sha256(value: Any, label: str) -> str:
    text = str(value).strip().lower()
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ConsensusBuilderError(f"{label} must be a lowercase SHA-256 digest.")
    return text


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _frame_sha256(frame: pd.DataFrame) -> str:
    text = frame.to_csv(index=False, lineterminator="\n", float_format="%.17g")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _frame_csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False, lineterminator="\n").encode("utf-8")


def _canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _pretty_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )
