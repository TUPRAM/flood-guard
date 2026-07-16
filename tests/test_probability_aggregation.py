from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

import pytest

from floodguard.probability_aggregation import (
    ProbabilityAggregationError,
    aggregate_probability_cells,
)


NODATA = -9999.0
ROOT = Path(__file__).resolve().parents[1]
MODEL_RUN_REQUIRED = tuple(
    json.loads(
        (ROOT / "packages/contracts/schemas/model-run.schema.json").read_text(
            encoding="utf-8"
        )
    )["required"]
)
FLOODGUARD_COMMIT = "58cb508acbfac43a21cf347259cf6d12beef533c"
GEOAI_COMMIT = "6833c8b71fb18f5b8ea17d5d9f8e0745157643c2"
CHANNEL_NAMES = [
    "pre_vv_db",
    "post_vv_db",
    "pre_vh_db",
    "post_vh_db",
    "vv_change_db",
    "vh_change_db",
    "slope",
    "permanent_water_flag",
]
TRANSFORM_RANGES = {
    "pre_vv_db": (-35.0, 5.0, "dB"),
    "post_vv_db": (-35.0, 5.0, "dB"),
    "pre_vh_db": (-45.0, 0.0, "dB"),
    "post_vh_db": (-45.0, 0.0, "dB"),
    "vv_change_db": (-20.0, 20.0, "dB"),
    "vh_change_db": (-20.0, 20.0, "dB"),
    "slope": (0.0, 60.0, "degrees"),
    "permanent_water_flag": (0.0, 1.0, "binary"),
}


def source_metadata(**overrides: object) -> dict[str, object]:
    metadata: dict[str, object] = {
        "schema_version": "1.0",
        "dataset_mode": "official_input",
        "operational_status": "planning_only",
        "run_status": "completed",
        "source_name": "Synthetic class-1 flood probability",
        "source_timestamp": "2024-09-15T23:16:01Z",
        "generated_at": "2024-09-16T00:00:00Z",
        "confidence_class": "medium",
        "assumptions": ["Synthetic values exercise the aggregation contract."],
        "official_warning": False,
        "data_version": "decision-bridge-contract-1",
        "git_commit": FLOODGUARD_COMMIT,
        "run_id": "geoai-official-001",
        "study_area": "synthetic_contract_grid",
        "model_family": "geoai",
        "geoai_version": "0.41.1",
        "geoai_commit": GEOAI_COMMIT,
        "model_id": "floodguard/synthetic-unet",
        "model_revision": "contract-proof-1",
        "model_sha256": "a" * 64,
        "architecture": "unet",
        "encoder": "resnet34",
        "encoder_weights": None,
        "num_channels": 8,
        "channel_names": list(CHANNEL_NAMES),
        "preprocessing": {
            "method": "fixed_clip_scale_to_uint8",
            "value_domain": "uint8_0_255",
            "sidecar_sha256": "b" * 64,
            "transforms": [
                {
                    "name": name,
                    "physical_min": TRANSFORM_RANGES[name][0],
                    "physical_max": TRANSFORM_RANGES[name][1],
                    "units": TRANSFORM_RANGES[name][2],
                    "description": f"Auditable fixed transform for {name}.",
                }
                for name in CHANNEL_NAMES
            ],
        },
        "input_manifest_rows": [
            {
                "product_id": "SYNTHETIC-PRE-001",
                "role": "pre_event_sar",
                "sha256": "c" * 64,
                "source_timestamp": "2024-09-10T00:00:00Z",
                "processing_allowed": True,
            },
            {
                "product_id": "SYNTHETIC-POST-001",
                "role": "post_event_sar",
                "sha256": "d" * 64,
                "source_timestamp": "2024-09-15T23:16:01Z",
                "processing_allowed": True,
            },
            {
                "product_id": "SYNTHETIC-MASK-001",
                "role": "reference_mask",
                "sha256": "2" * 64,
                "source_timestamp": "2024-09-15T23:16:01Z",
                "processing_allowed": True,
            },
            {
                "product_id": "SYNTHETIC-SLOPE-001",
                "role": "terrain_slope",
                "sha256": "4" * 64,
                "source_timestamp": "2024-09-01T00:00:00Z",
                "processing_allowed": True,
            },
            {
                "product_id": "SYNTHETIC-WATER-001",
                "role": "permanent_water",
                "sha256": "5" * 64,
                "source_timestamp": "2024-09-01T00:00:00Z",
                "processing_allowed": True,
            },
        ],
        "encoded_feature_sha256": "e" * 64,
        "reference_mask_sha256": "2" * 64,
        "prepared_tile_manifest_sha256": "3" * 64,
        "spatial_holdout_ids": ["synthetic-block-east"],
        "spatial_partitions": [
            {
                "spatial_group_id": "synthetic-block-west",
                "split": "train",
                "bounds": [600000.0, 2200000.0, 600160.0, 2200320.0],
            },
            {
                "spatial_group_id": "synthetic-block-east",
                "split": "holdout",
                "bounds": [600160.0, 2200000.0, 600320.0, 2200320.0],
            },
        ],
        "reference_mask_id": "SYNTHETIC-MASK-001",
        "processing_scope": "cleared_probability_contract_test",
        "reference_mask_status": "confirmed_for_model_purpose",
        "target_crs": "EPSG:32647",
        "resolution": [10.0, 10.0],
        "bounds": [600000.0, 2200000.0, 600320.0, 2200320.0],
        "tile_size": 16,
        "overlap": 4,
        "stride": 12,
        "batch_size": 1,
        "device": "cpu",
        "flood_class_index": 1,
        "probability_threshold": 0.5,
        "external_output_workspace": "external-workspace/geoai-official-001",
        "processing_allowed": True,
        "can_feed_decision_layer": True,
        "reason_blocked": "",
        "validation_metrics": {
            "iou": 0.8,
            "f1_dice": 0.88,
            "precision": 0.9,
            "recall": 0.86,
            "area_error_ratio": 0.1,
            "brier_score": 0.08,
            "expected_calibration_error": 0.04,
        },
        "error_categories": [],
    }
    metadata.update(overrides)
    return metadata


def canonical_manifest_sha256(manifest: object) -> str:
    try:
        encoded = json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        return "0" * 64
    return hashlib.sha256(encoded).hexdigest()


def probability_raster_receipt(
    metadata: object,
    **overrides: object,
) -> dict[str, object]:
    run_id = (
        metadata.get("run_id", "missing-run")
        if isinstance(metadata, dict)
        else "missing-run"
    )
    receipt: dict[str, object] = {
        "run_id": run_id,
        "model_run_manifest_sha256": canonical_manifest_sha256(metadata),
        "probability_raster_sha256": "f" * 64,
        "grid": {
            "crs": "EPSG:32647",
            "transform": [
                10.0,
                0.0,
                600000.0,
                0.0,
                -10.0,
                2200320.0,
                0.0,
                0.0,
                1.0,
            ],
            "width": 32,
            "height": 32,
            "bounds": [600000.0, 2200000.0, 600320.0, 2200320.0],
            "count": 1,
            "dtypes": ["float32"],
            "descriptions": ["flood_probability_0_1"],
            "nodata": NODATA,
        },
    }
    receipt.update(overrides)
    return receipt


def aggregate(
    probabilities: object = (0.1, NODATA, 0.5, 0.9),
    **overrides: object,
) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "subdistrict_id": "TH570906",
        "subdistrict_name": "Wiang Phang Kham",
        "nodata": NODATA,
        "probability_threshold": 0.5,
        "source_metadata": source_metadata(),
    }
    kwargs.update(overrides)
    metadata = kwargs["source_metadata"]
    if (
        "probability_raster_receipt" not in kwargs
        and isinstance(metadata, dict)
        and metadata.get("can_feed_decision_layer") is True
    ):
        kwargs["probability_raster_receipt"] = probability_raster_receipt(metadata)
    return aggregate_probability_cells(
        probabilities,  # type: ignore[arg-type]
        **kwargs,
    )


def test_caller_supplied_cells_cannot_become_decision_eligible() -> None:
    with pytest.raises(
        ProbabilityAggregationError,
        match="trusted raster-and-zonal extraction adapter",
    ):
        aggregate()


def test_single_valid_probability_has_stable_p90() -> None:
    candidate = source_metadata(
        dataset_mode="candidate",
        can_feed_decision_layer=False,
        reason_blocked="Candidate model evidence is report-only.",
    )
    result = aggregate(
        (NODATA, 0.37, NODATA),
        source_metadata=candidate,
        allow_report_only=True,
    )
    assert result["mean_flood_probability_0_1"] == pytest.approx(0.37)
    assert result["p90_flood_probability_0_1"] == pytest.approx(0.37)
    assert result["sample_pixel_count"] == 1


def test_candidate_requires_explicit_report_only_and_is_never_eligible() -> None:
    candidate = source_metadata(
        dataset_mode="candidate",
        can_feed_decision_layer=False,
        reason_blocked="Candidate model evidence is report-only.",
    )

    with pytest.raises(ProbabilityAggregationError, match="allow_report_only=True"):
        aggregate(source_metadata=candidate)

    result = aggregate(source_metadata=candidate, allow_report_only=True)
    assert result["processing_allowed"] is True
    assert result["can_feed_decision_layer"] is False
    assert result["eligible_for_decision_layer"] is False
    assert result["eligible_for_fpps"] is False
    assert result["aggregation_status"] == "report_only"
    assert result["reason_blocked"] == "Candidate model evidence is report-only."


def test_blocked_source_can_only_be_summarized_as_report_only() -> None:
    blocked = source_metadata(
        processing_allowed=False,
        can_feed_decision_layer=False,
        reason_blocked="Reference-mask and provenance gates remain blocked.",
    )
    with pytest.raises(ProbabilityAggregationError, match="processing_allowed=false"):
        aggregate(source_metadata=blocked)

    result = aggregate(source_metadata=blocked, allow_report_only=True)
    assert result["processing_allowed"] is False
    assert result["can_feed_decision_layer"] is False
    assert result["eligible_for_decision_layer"] is False


@pytest.mark.parametrize(
    "metadata",
    [
        source_metadata(dataset_mode="candidate"),
        source_metadata(processing_allowed=False),
    ],
)
def test_contradictory_source_promotion_flags_are_rejected(
    metadata: dict[str, object],
) -> None:
    with pytest.raises(ProbabilityAggregationError, match="can_feed_decision_layer"):
        aggregate(source_metadata=metadata, allow_report_only=True)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("operational_status", "non_operational"),
        ("run_status", "blocked"),
        ("confidence_class", "low"),
        ("reference_mask_status", "synthetic_fixture_only"),
        ("reason_blocked", "Reference evidence remains blocked."),
    ],
)
def test_decision_feed_requires_complete_promotion_receipt(
    field: str,
    value: object,
) -> None:
    metadata = source_metadata(**{field: value})
    with pytest.raises(ProbabilityAggregationError, match="promotion evidence"):
        aggregate(source_metadata=metadata)

    incomplete_metrics = source_metadata()
    metrics = dict(incomplete_metrics["validation_metrics"])  # type: ignore[arg-type]
    metrics["expected_calibration_error"] = None
    incomplete_metrics["validation_metrics"] = metrics
    with pytest.raises(
        ProbabilityAggregationError, match="validation_metrics=incomplete"
    ):
        aggregate(source_metadata=incomplete_metrics)


def test_report_only_source_requires_explicit_blocked_reason() -> None:
    blocked = source_metadata(
        dataset_mode="fixture_demo",
        can_feed_decision_layer=False,
        reason_blocked="",
    )
    with pytest.raises(ProbabilityAggregationError, match="reason_blocked"):
        aggregate(source_metadata=blocked, allow_report_only=True)


@pytest.mark.parametrize("invalid", [-0.001, 1.001, math.inf, -math.inf, math.nan])
def test_invalid_probability_cells_are_rejected(invalid: float) -> None:
    with pytest.raises(ProbabilityAggregationError, match=r"probabilities\[1\]"):
        aggregate((0.2, invalid, 0.8))


@pytest.mark.parametrize("invalid", [None, "0.5", True, object()])
def test_non_numeric_probability_cells_are_rejected(invalid: object) -> None:
    with pytest.raises(ProbabilityAggregationError, match=r"probabilities\[1\]"):
        aggregate((0.2, invalid, 0.8))


@pytest.mark.parametrize("invalid_nodata", [0.0, 0.5, 1.0, math.nan, math.inf])
def test_nodata_must_be_finite_and_separate_from_probability_values(
    invalid_nodata: float,
) -> None:
    with pytest.raises(ProbabilityAggregationError, match="nodata"):
        aggregate((0.2, 0.8), nodata=invalid_nodata)


def test_all_nodata_cells_are_rejected() -> None:
    with pytest.raises(ProbabilityAggregationError, match="at least one valid"):
        aggregate((NODATA, NODATA))


@pytest.mark.parametrize("threshold", [-0.1, 1.1, math.nan, math.inf, "0.5"])
def test_invalid_probability_threshold_is_rejected(threshold: object) -> None:
    with pytest.raises(ProbabilityAggregationError, match="probability_threshold"):
        aggregate(probability_threshold=threshold)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("source_name", "", "source_name"),
        ("source_timestamp", "2024-09-15", "source_timestamp"),
        ("confidence_class", "unknown", "confidence_class"),
        ("assumptions", "not a list", "assumptions"),
        ("assumptions", [], "assumptions"),
        ("processing_scope", "", "processing_scope"),
        ("operational_status", "unknown", "operational_status"),
        ("run_status", "unknown", "run_status"),
        ("reference_mask_status", "", "reference_mask_status"),
        ("validation_metrics", "not a mapping", "validation_metrics"),
        ("processing_allowed", 1, "processing_allowed"),
        ("can_feed_decision_layer", "true", "can_feed_decision_layer"),
    ],
)
def test_invalid_source_metadata_is_rejected(
    field: str,
    value: object,
    message: str,
) -> None:
    metadata = source_metadata()
    metadata[field] = value
    with pytest.raises(ProbabilityAggregationError, match=message):
        aggregate(source_metadata=metadata)


def test_missing_source_metadata_field_is_rejected() -> None:
    metadata = source_metadata()
    del metadata["source_timestamp"]
    with pytest.raises(ProbabilityAggregationError, match="source_timestamp"):
        aggregate(source_metadata=metadata)


def test_source_metadata_is_copied_without_mutation() -> None:
    metadata = source_metadata(
        dataset_mode="candidate",
        can_feed_decision_layer=False,
        reason_blocked="Candidate model evidence is report-only.",
    )
    before = deepcopy(metadata)
    result = aggregate(source_metadata=metadata, allow_report_only=True)

    assert metadata == before
    assert result["assumptions"] == metadata["assumptions"]
    assert result["assumptions"] is not metadata["assumptions"]


@pytest.mark.parametrize("field", MODEL_RUN_REQUIRED)
def test_decision_feed_requires_every_shared_model_run_field(field: str) -> None:
    metadata = source_metadata()
    del metadata[field]

    with pytest.raises(
        ProbabilityAggregationError,
        match="required fields|schema-complete",
    ):
        aggregate(source_metadata=metadata)


def test_decision_feed_rejects_model_run_additional_properties() -> None:
    metadata = source_metadata(undeclared_provenance="not allowed")

    with pytest.raises(ProbabilityAggregationError, match="unsupported fields"):
        aggregate(source_metadata=metadata)


def test_complete_caller_authored_receipts_still_cannot_authorize_cells() -> None:
    metadata = source_metadata()
    receipt = probability_raster_receipt(metadata)

    with pytest.raises(
        ProbabilityAggregationError,
        match="trusted raster-and-zonal extraction adapter",
    ):
        aggregate(
            source_metadata=metadata,
            probability_raster_receipt=receipt,
        )


def test_report_only_mode_accepts_legacy_minimal_metadata_without_raster_receipt() -> (
    None
):
    metadata = {
        "dataset_mode": "candidate",
        "operational_status": "non_operational",
        "run_status": "completed",
        "source_name": "Legacy research-only probability",
        "source_timestamp": "2024-09-15T23:16:01Z",
        "confidence_class": "low",
        "assumptions": ["No decision-feed provenance is claimed."],
        "processing_scope": "research_report_only",
        "reference_mask_status": "synthetic_fixture_only",
        "processing_allowed": True,
        "can_feed_decision_layer": False,
        "reason_blocked": "A complete model-run and raster receipt are absent.",
        "validation_metrics": source_metadata()["validation_metrics"],
    }

    result = aggregate(
        source_metadata=metadata,
        probability_raster_receipt=None,
        allow_report_only=True,
    )

    assert result["aggregation_status"] == "report_only"
    assert result["run_id"] is None
    assert result["probability_raster_sha256"] is None


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("model_sha256", None, "model_sha256"),
        ("encoded_feature_sha256", "A" * 64, "encoded_feature_sha256"),
        ("reference_mask_sha256", "short", "reference_mask_sha256"),
        ("prepared_tile_manifest_sha256", None, "prepared_tile_manifest_sha256"),
    ],
)
def test_decision_feed_rejects_absent_or_invalid_artifact_checksums(
    field: str,
    value: object,
    message: str,
) -> None:
    metadata = source_metadata(**{field: value})

    with pytest.raises(ProbabilityAggregationError, match=message):
        aggregate(source_metadata=metadata)


def test_decision_feed_rejects_invalid_preprocessing_sidecar_checksum() -> None:
    metadata = source_metadata()
    preprocessing = deepcopy(metadata["preprocessing"])
    preprocessing["sidecar_sha256"] = None
    metadata["preprocessing"] = preprocessing

    with pytest.raises(ProbabilityAggregationError, match="sidecar_sha256"):
        aggregate(source_metadata=metadata)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("blocked_license", "licensing"),
        ("bad_checksum", "sha256"),
        ("missing_ancillary", "terrain_slope"),
        ("duplicate_product", "product IDs"),
        ("bad_timing", "timing"),
        ("reference_mismatch", "Reference-mask"),
    ],
)
def test_decision_feed_validates_input_receipts_and_licensing(
    mutation: str,
    message: str,
) -> None:
    metadata = source_metadata()
    rows = deepcopy(metadata["input_manifest_rows"])
    if mutation == "blocked_license":
        rows[0]["processing_allowed"] = False
    elif mutation == "bad_checksum":
        rows[0]["sha256"] = "not-a-checksum"
    elif mutation == "missing_ancillary":
        rows = [row for row in rows if row["role"] != "terrain_slope"]
    elif mutation == "duplicate_product":
        rows[1]["product_id"] = rows[0]["product_id"]
    elif mutation == "bad_timing":
        rows[0]["source_timestamp"] = rows[1]["source_timestamp"]
    elif mutation == "reference_mismatch":
        rows[2]["sha256"] = "6" * 64
    metadata["input_manifest_rows"] = rows

    with pytest.raises(ProbabilityAggregationError, match=message):
        aggregate(source_metadata=metadata)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("raw_domain", "raw physical"),
        ("wrong_method", "preprocessing method"),
        ("wrong_order", "names and order"),
        ("invalid_range", "physical_min"),
    ],
)
def test_decision_feed_validates_auditable_preprocessing(
    mutation: str,
    message: str,
) -> None:
    metadata = source_metadata()
    preprocessing = deepcopy(metadata["preprocessing"])
    if mutation == "raw_domain":
        preprocessing["value_domain"] = "physical_units"
    elif mutation == "wrong_method":
        preprocessing["method"] = "implicit_divide_255"
    elif mutation == "wrong_order":
        preprocessing["transforms"][0], preprocessing["transforms"][1] = (
            preprocessing["transforms"][1],
            preprocessing["transforms"][0],
        )
    elif mutation == "invalid_range":
        preprocessing["transforms"][0]["physical_max"] = preprocessing["transforms"][0][
            "physical_min"
        ]
    metadata["preprocessing"] = preprocessing

    with pytest.raises(ProbabilityAggregationError, match=message):
        aggregate(source_metadata=metadata)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("git_commit", "abc1234", "40-character Git commit"),
        ("geoai_version", None, "geoai_version"),
        ("geoai_version", "0.40.0", "geoai_version=0.41.1"),
        ("geoai_commit", None, "geoai_commit"),
        ("geoai_commit", "0" * 40, "reviewed source"),
        ("model_id", None, "model_id"),
        ("model_revision", "", "model_revision"),
        ("architecture", None, "architecture"),
        ("encoder", None, "encoder"),
    ],
)
def test_decision_feed_rejects_invalid_git_geoai_and_model_provenance(
    field: str,
    value: object,
    message: str,
) -> None:
    metadata = source_metadata(**{field: value})

    with pytest.raises(ProbabilityAggregationError, match=message):
        aggregate(source_metadata=metadata)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tile_size", 0),
        ("overlap", 16),
        ("stride", 11),
        ("batch_size", 0),
    ],
)
def test_decision_feed_rejects_invalid_tile_receipt(
    field: str,
    value: object,
) -> None:
    metadata = source_metadata(**{field: value})

    with pytest.raises(
        ProbabilityAggregationError,
        match=field if field in {"tile_size", "batch_size"} else "tile receipt",
    ):
        aggregate(source_metadata=metadata)


def test_decision_feed_requires_probability_raster_receipt() -> None:
    with pytest.raises(ProbabilityAggregationError, match="probability_raster_receipt"):
        aggregate(probability_raster_receipt=None)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("run_id", "different-run", "run_id"),
        ("model_run_manifest_sha256", "0" * 64, "exact model-run manifest"),
        ("probability_raster_sha256", "invalid", "probability_raster_sha256"),
    ],
)
def test_decision_feed_binds_raster_run_manifest_and_checksum(
    field: str,
    value: object,
    message: str,
) -> None:
    metadata = source_metadata()
    receipt = probability_raster_receipt(metadata, **{field: value})

    with pytest.raises(ProbabilityAggregationError, match=message):
        aggregate(
            source_metadata=metadata,
            probability_raster_receipt=receipt,
        )


def test_decision_feed_rejects_stale_manifest_binding_after_metadata_change() -> None:
    metadata = source_metadata()
    receipt = probability_raster_receipt(metadata)
    metadata["model_revision"] = "contract-proof-2"

    with pytest.raises(ProbabilityAggregationError, match="exact model-run manifest"):
        aggregate(
            source_metadata=metadata,
            probability_raster_receipt=receipt,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("crs", "EPSG:4326", "CRS"),
        ("width", 31, "dimensions"),
        ("bounds", [600000.0, 2200000.0, 600310.0, 2200320.0], "bounds"),
        ("transform", [1.0] * 9, "transform"),
        ("count", 2, "one class-1"),
        ("dtypes", ["uint8"], "one float32"),
        ("descriptions", ["class_1"], "one float32"),
        ("nodata", -32768.0, "nodata"),
    ],
)
def test_decision_feed_binds_probability_grid(
    field: str,
    value: object,
    message: str,
) -> None:
    metadata = source_metadata()
    receipt = probability_raster_receipt(metadata)
    grid = deepcopy(receipt["grid"])
    grid[field] = value
    receipt["grid"] = grid

    with pytest.raises(ProbabilityAggregationError, match=message):
        aggregate(
            source_metadata=metadata,
            probability_raster_receipt=receipt,
        )


def test_decision_feed_binds_probability_threshold_to_model_run() -> None:
    metadata = source_metadata(probability_threshold=0.6)

    with pytest.raises(ProbabilityAggregationError, match="probability_threshold"):
        aggregate(source_metadata=metadata, probability_threshold=0.5)
