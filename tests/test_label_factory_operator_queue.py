from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from floodguard.label_factory.operator_queue import (
    FIXED_SAFETY_FIELDS,
    OPERATOR_QUEUE_MANIFEST_SCHEMA,
    OperatorQueueError,
    build_operator_queue,
    validate_operator_queue_manifest,
    write_operator_queue_package,
)
from floodguard.label_factory.review_bundle import (
    SENSITIVE_REVIEW_COLUMNS,
    ReviewPurpose,
    build_blinded_review_manifest,
)


EVENT_ID = "TH-MAESAI-2024-09"
GRID_HASH = "a" * 64


def _acquisition() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for index, lane in enumerate(("active", "hard_stratum", "random_control", "active")):
        rows.append(
            {
                "query_region_id": f"Q-{index}",
                "tile_id": f"T-{index}",
                "event_id": EVENT_ID,
                "grid_id": "UTM47N_10M",
                "grid_contract_sha256": GRID_HASH,
                "source_registry_sha256": "b" * 64,
                "processing_alignment_receipt_sha256": "c" * 64,
                "pre_source_asset_ids": "S1-PRE",
                "event_source_asset_ids": "S1-EVENT",
                "pre_product_ids": "PRE-PRODUCT",
                "event_product_ids": "EVENT-PRODUCT",
                "pre_acquisition_utc": "2024-09-03T23:16:00Z",
                "event_acquisition_utc": "2024-09-15T23:16:00Z",
                "pre_source_sha256s": "d" * 64,
                "event_source_sha256s": "e" * 64,
                "feature_schema_version": "sar_change_v2",
                "query_size_pixels": 32,
                "resolution_m": 10,
                "bbox_min_x": 1000 + index * 500,
                "bbox_min_y": 2000,
                "bbox_max_x": 1320 + index * 500,
                "bbox_max_y": 2320,
                "crs": "EPSG:32647",
                "dataset_role": "training_and_query_pool",
                "review_status": "unreviewed",
                "eligible_for_human_annotation": True,
                "eligible_for_active_selection": True,
                "eligible_for_review_queue": True,
                "query_model_only": True,
                "eligible_for_decision_layer": False,
                "eligible_for_fpps": False,
                "eligible_for_warning": False,
                "selection_creates_flood_truth": False,
                "source_timestamp": "2024-09-15T23:16:00Z",
                "confidence_class": "low",
                "assumptions": "Internal query evidence, not flood truth.",
                "selected": index < 3,
                "selection_lane": lane if index < 3 else "",
                "selection_order": index + 1 if index < 3 else "",
                # These are the names emitted by the region candidate bridge;
                # the operator package normalizes them to explicit query-score
                # names while also accepting committee-score aliases.
                "mean_logistic_probability": 0.4 + index * 0.05,
                "mean_boosted_probability": 0.6 - index * 0.05,
                "uncertainty": 0.9 - index * 0.1,
                "absolute_disagreement": 0.2 - index * 0.02,
                "jensen_shannon_disagreement": 0.1 - index * 0.01,
                "active_score": 0.95 - index * 0.1,
                "uncertainty_rank": 1 - index * 0.1,
                "disagreement_rank": 0.9 - index * 0.1,
                "boundary_rank": 0.8 - index * 0.1,
                "boundary_impurity": 0.3,
            }
        )
    return pd.DataFrame(rows)


def _context() -> pd.DataFrame:
    rows = []
    for index in range(4):
        rows.append(
            {
                "query_region_id": f"Q-{index}",
                "tile_id": f"T-{index}",
                "event_id": EVENT_ID,
                "grid_id": "UTM47N_10M",
                "grid_contract_sha256": GRID_HASH,
                "wgs84_min_longitude": 99.80 + index * 0.001,
                "wgs84_min_latitude": 20.40,
                "wgs84_max_longitude": 99.801 + index * 0.001,
                "wgs84_max_latitude": 20.401,
                "permanent_water_fraction": 0.1,
                "worldcover_water_fraction": 0.0,
                "urban_fraction": 0.25 if index == 1 else 0.0,
                "forest_fraction": 0.5 if index == 0 else 0.1,
                "cropland_fraction": 0.1,
                "steep_terrain_fraction": 0.5 if index == 2 else 0.0,
                "slope_p90_degrees": 20 if index == 2 else 4,
                "round0_stratum": ("forest", "urban", "steep_terrain", "other_context")[
                    index
                ],
                "major_land_cover_stratum": ("forest", "urban", "forest", "other")[
                    index
                ],
                "hard_stratum": index in {1, 2},
            }
        )
    return pd.DataFrame(rows)


def _weak() -> pd.DataFrame:
    rows = []
    for index in range(4):
        rows.append(
            {
                "query_region_id": f"Q-{index}",
                "tile_id": f"T-{index}",
                "event_id": EVENT_ID,
                "grid_contract_sha256": GRID_HASH,
                "weak_label": "weak_positive" if index == 0 else "weak_unreviewed",
                "weak_positive_fraction": 0.75 if index == 0 else 0.0,
                "weak_uncertain_fraction": 0.25 if index == 0 else 0.0,
                "weak_unreviewed_fraction": 0.0 if index == 0 else 1.0,
                "weak_boundary_query": index == 0,
                "weak_source_type": "positive_unlabeled_weak_seed",
                "weak_source_sha256": "f" * 64,
                "weak_summary_manifest_sha256": "1" * 64,
            }
        )
    return pd.DataFrame(rows)


def _previews() -> pd.DataFrame:
    rows = []
    for index in range(4):
        rows.append(
            {
                "query_region_id": f"Q-{index}",
                "tile_id": f"T-{index}",
                "event_id": EVENT_ID,
                "grid_contract_sha256": GRID_HASH,
                "preview_path": f"previews/Q-{index}.png",
                "preview_sha256": str(index + 2) * 64,
                "preview_manifest_sha256": "9" * 64,
            }
        )
    return pd.DataFrame(rows)


def test_operator_queue_joins_selected_internal_evidence_and_safety() -> None:
    result = build_operator_queue(
        _acquisition(),
        context_evidence=_context(),
        weak_summary=_weak(),
        preview_manifest=_previews(),
    )

    assert result["query_region_id"].tolist() == ["Q-0", "Q-1", "Q-2"]
    assert result["mean_logistic_query_score"].tolist() == pytest.approx([0.4, 0.45, 0.5])
    assert result["mean_boosted_query_score"].tolist() == pytest.approx([0.6, 0.55, 0.5])
    assert result["mean_committee_query_score"].tolist() == pytest.approx([0.5, 0.5, 0.5])
    assert result["entropy_score"].tolist() == pytest.approx([0.9, 0.8, 0.7])
    assert result["context_stratum"].tolist() == ["forest", "urban", "steep_terrain"]
    assert result["recommended_review_priority"].tolist() == [
        "high_active_learning",
        "high_systematic_error",
        "required_random_control",
    ]
    assert result["preview_path"].tolist() == [
        "previews/Q-0.png",
        "previews/Q-1.png",
        "previews/Q-2.png",
    ]
    assert result["weak_evidence_semantics"].eq(
        "positive_unlabeled_operator_context_only"
    ).all()
    for field, expected in FIXED_SAFETY_FIELDS.items():
        assert result[field].eq(expected).all()


@pytest.mark.parametrize("failure", ["duplicate", "missing", "event", "tile", "grid"])
def test_auxiliary_join_fails_closed(failure: str) -> None:
    context = _context()
    if failure == "duplicate":
        context = pd.concat([context, context.iloc[[0]]], ignore_index=True)
        message = "duplicate query_region_id"
    elif failure == "missing":
        context = context[context["query_region_id"] != "Q-1"]
        message = "missing selected query"
    elif failure == "event":
        context.loc[1, "event_id"] = "TH-OTHER-2024-09"
        message = "event_id"
    elif failure == "tile":
        context.loc[1, "tile_id"] = "OTHER-TILE"
        message = "tile_id"
    else:
        context.loc[1, "grid_contract_sha256"] = "9" * 64
        message = "grid_contract_sha256"

    with pytest.raises(OperatorQueueError, match=message):
        build_operator_queue(_acquisition(), context_evidence=context)


def test_operator_queue_rejects_unsafe_or_incomplete_evidence() -> None:
    unsafe = _acquisition()
    unsafe.loc[0, "eligible_for_fpps"] = True
    with pytest.raises(OperatorQueueError, match="eligible_for_fpps"):
        build_operator_queue(unsafe, context_evidence=_context())

    no_wgs84 = _context().drop(columns=list(_context().filter(like="wgs84_").columns))
    with pytest.raises(OperatorQueueError, match="WGS84 bounds"):
        build_operator_queue(_acquisition(), context_evidence=no_wgs84)

    weak = _weak()
    weak.loc[0, "weak_positive_fraction"] = 0.5
    with pytest.raises(OperatorQueueError, match="must sum to 1"):
        build_operator_queue(
            _acquisition(), context_evidence=_context(), weak_summary=weak
        )

    previews = _previews()
    previews.loc[0, "preview_sha256"] = "not-a-sha"
    with pytest.raises(OperatorQueueError, match="preview_sha256"):
        build_operator_queue(
            _acquisition(), context_evidence=_context(), preview_manifest=previews
        )


def test_file_preview_manifest_verifies_selected_preview_bytes(tmp_path: Path) -> None:
    preview_dir = tmp_path / "previews"
    preview_dir.mkdir()
    previews = _previews()
    for index in range(3):
        payload = f"query-preview-{index}".encode("utf-8")
        preview = preview_dir / f"Q-{index}.png"
        preview.write_bytes(payload)
        previews.loc[index, "preview_sha256"] = hashlib.sha256(payload).hexdigest()
    # The unselected row may refer to a file not yet rendered; only package rows
    # are resolved and verified.
    preview_manifest = tmp_path / "preview_manifest.csv"
    previews.to_csv(preview_manifest, index=False)

    result = build_operator_queue(
        _acquisition(),
        context_evidence=_context(),
        preview_manifest=preview_manifest,
    )
    assert result["preview_supplied"].all()

    (preview_dir / "Q-1.png").write_bytes(b"tampered")
    with pytest.raises(OperatorQueueError, match="checksum mismatch"):
        build_operator_queue(
            _acquisition(),
            context_evidence=_context(),
            preview_manifest=preview_manifest,
        )


def test_package_is_write_once_and_manifest_is_self_hashed(tmp_path: Path) -> None:
    target = tmp_path / "operator_round_1"
    written = write_operator_queue_package(
        _acquisition(),
        output_dir=target,
        context_evidence=_context(),
        weak_summary=_weak(),
        preview_manifest=_previews(),
        generated_at_utc="2026-07-12T00:00:00Z",
    )
    payload = validate_operator_queue_manifest(written["manifest"])

    assert payload["artifact_schema"] == OPERATOR_QUEUE_MANIFEST_SCHEMA
    assert payload["row_count"] == 3
    assert payload["query_region_ids"] == ["Q-0", "Q-1", "Q-2"]
    assert len(payload["manifest_sha256"]) == 64
    assert len(payload["source_inputs"]) == 4
    with pytest.raises(OperatorQueueError, match="write-once"):
        write_operator_queue_package(
            _acquisition(), output_dir=target, context_evidence=_context()
        )

    manifest = json.loads(written["manifest"].read_text(encoding="utf-8"))
    manifest["row_count"] = 4
    written["manifest"].write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(OperatorQueueError, match="self-hash mismatch"):
        validate_operator_queue_manifest(written["manifest"])


def test_blinded_manifest_never_exposes_operator_or_model_evidence() -> None:
    operator = build_operator_queue(
        _acquisition(),
        context_evidence=_context(),
        weak_summary=_weak(),
        preview_manifest=_previews(),
    )
    visible = build_blinded_review_manifest(
        operator,
        review_purpose=ReviewPurpose.ACQUISITION_PRIMARY,
    )

    forbidden = {
        "operator_internal_only",
        "recommended_review_priority",
        "mean_logistic_query_score",
        "mean_boosted_query_score",
        "entropy_score",
        "absolute_disagreement",
        "weak_label",
        "weak_positive_fraction",
        "preview_path",
        "preview_sha256",
        "selection_lane",
        "selection_order",
    }
    assert forbidden - {"selection_lane", "selection_order"} <= SENSITIVE_REVIEW_COLUMNS
    assert forbidden.isdisjoint(visible.columns)
    assert set(visible["query_region_id"]) == {"Q-0", "Q-1", "Q-2"}
