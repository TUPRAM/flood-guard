from __future__ import annotations

from copy import deepcopy
import hashlib
import hmac
import json
import math
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import transform_geom

import floodguard.trusted_zonal_adapter as trusted_zonal_module
import floodguard.trusted_zonal_cli as trusted_zonal_cli_module
from floodguard.probability_aggregation import (
    ProbabilityAggregationError,
    aggregate_probability_cells,
)
from floodguard.trusted_zonal_adapter import (
    create_signed_zonal_receipt,
    verify_signed_zonal_receipt,
)
from floodguard.trusted_zonal_cli import main as zonal_cli_main


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


ZONAL_SIGNING_KEY = b"floodguard-zonal-test-signing-key-0001"
ZONAL_KEY_ID = "test/zonal-key-2026-01"
ZONAL_GENERATED_AT = "2024-09-16T01:00:00Z"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_probability_raster(
    path: Path,
    *,
    values: np.ndarray | None = None,
    crs: str = "EPSG:32647",
    transform: object | None = None,
    dtype: str = "float32",
    description: str = "flood_probability_0_1",
    nodata: float = NODATA,
) -> Path:
    if values is None:
        values = np.full((32, 32), 0.2, dtype=np.float32)
        values[:, 16:] = 0.8
        values[0, 0] = NODATA
    transform = transform or from_origin(600000.0, 2200320.0, 10.0, 10.0)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=values.shape[1],
        height=values.shape[0],
        count=1,
        dtype=dtype,
        crs=crs,
        transform=transform,
        nodata=nodata,
    ) as dataset:
        dataset.write(values.astype(dtype), 1)
        dataset.set_band_description(1, description)
    return path


def polygon_geometry(
    left: float, bottom: float, right: float, top: float
) -> dict[str, object]:
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [left, bottom],
                [right, bottom],
                [right, top],
                [left, top],
                [left, bottom],
            ]
        ],
    }


def default_area_features() -> list[dict[str, object]]:
    # Deliberately reversed: the adapter must emit stable ID ordering.
    return [
        {
            "type": "Feature",
            "properties": {"ADM_ID": "AREA-B", "ADM_NAME": "East"},
            "geometry": polygon_geometry(600160.0, 2200000.0, 600320.0, 2200320.0),
        },
        {
            "type": "Feature",
            "properties": {"ADM_ID": "AREA-A", "ADM_NAME": "West"},
            "geometry": polygon_geometry(600000.0, 2200000.0, 600160.0, 2200320.0),
        },
    ]


def write_area_geojson(
    path: Path,
    *,
    features: list[dict[str, object]] | None = None,
    crs: str | None = "EPSG:32647",
) -> Path:
    document: dict[str, object] = {
        "type": "FeatureCollection",
        "features": features if features is not None else default_area_features(),
    }
    if crs is not None:
        document["crs"] = {"type": "name", "properties": {"name": crs}}
    path.write_text(
        json.dumps(document, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    return path


def geometry_lineage(path: Path, **overrides: object) -> dict[str, object]:
    receipt: dict[str, object] = {
        "dataset_id": "TH-ADMIN-AUTH-001",
        "data_version": "2024-09-reviewed",
        "sha256": file_sha256(path),
        "source_name": "Qualified authoritative administrative geometry",
        "source_timestamp": "2024-09-01T00:00:00Z",
        "crs": "EPSG:32647",
        "area_id_field": "ADM_ID",
        "area_name_field": "ADM_NAME",
        "feature_count": 2,
        "authority_status": "authoritative_for_study_area",
        "processing_allowed": True,
    }
    receipt.update(overrides)
    return receipt


def zonal_contract(
    tmp_path: Path,
    *,
    raster_values: np.ndarray | None = None,
    raster_crs: str = "EPSG:32647",
    raster_transform: object | None = None,
    raster_dtype: str = "float32",
    raster_description: str = "flood_probability_0_1",
    features: list[dict[str, object]] | None = None,
    geometry_crs: str | None = "EPSG:32647",
    geometry_overrides: dict[str, object] | None = None,
    metadata_overrides: dict[str, object] | None = None,
) -> dict[str, object]:
    raster_path = write_probability_raster(
        tmp_path / "probability.tif",
        values=raster_values,
        crs=raster_crs,
        transform=raster_transform,
        dtype=raster_dtype,
        description=raster_description,
    )
    geometry_path = write_area_geojson(
        tmp_path / "areas.geojson", features=features, crs=geometry_crs
    )
    metadata = source_metadata(**(metadata_overrides or {}))
    raster_receipt = probability_raster_receipt(
        metadata, probability_raster_sha256=file_sha256(raster_path)
    )
    geometry_receipt = geometry_lineage(geometry_path, **(geometry_overrides or {}))
    return {
        "raster_path": raster_path,
        "geometry_path": geometry_path,
        "metadata": metadata,
        "raster_receipt": raster_receipt,
        "geometry_receipt": geometry_receipt,
    }


def create_zonal(contract: dict[str, object], **overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "probability_raster_path": contract["raster_path"],
        "authoritative_geometry_path": contract["geometry_path"],
        "source_metadata": contract["metadata"],
        "probability_raster_receipt": contract["raster_receipt"],
        "authoritative_geometry_receipt": contract["geometry_receipt"],
        "signing_key": ZONAL_SIGNING_KEY,
        "key_id": ZONAL_KEY_ID,
        "generated_at": ZONAL_GENERATED_AT,
    }
    kwargs.update(overrides)
    return create_signed_zonal_receipt(**kwargs)  # type: ignore[arg-type]


def verify_zonal(
    receipt: dict[str, object], contract: dict[str, object], **overrides: object
) -> list[dict[str, object]]:
    kwargs: dict[str, object] = {
        "signing_key": ZONAL_SIGNING_KEY,
        "expected_key_id": ZONAL_KEY_ID,
        "source_metadata": contract["metadata"],
        "probability_raster_receipt": contract["raster_receipt"],
        "authoritative_geometry_receipt": contract["geometry_receipt"],
    }
    kwargs.update(overrides)
    return verify_signed_zonal_receipt(receipt, **kwargs)  # type: ignore[arg-type]


def resign_zonal(receipt: dict[str, object], key: bytes = ZONAL_SIGNING_KEY) -> None:
    unsigned = deepcopy(receipt)
    unsigned["signature"] = {
        name: value for name, value in unsigned["signature"].items() if name != "value"
    }
    encoded = json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    signature = deepcopy(receipt["signature"])
    signature["value"] = hmac.new(key, encoded, hashlib.sha256).hexdigest()
    receipt["signature"] = signature


def test_trusted_zonal_adapter_derives_signs_and_verifies_area_statistics(
    tmp_path: Path,
) -> None:
    contract = zonal_contract(tmp_path)
    receipt = create_zonal(contract)

    assert receipt["receipt_type"] == "floodguard.trusted_probability_zonal"
    assert receipt["can_feed_decision_layer"] is True
    assert receipt["eligible_for_decision_layer"] is True
    assert receipt["eligible_for_fpps"] is True
    assert receipt["key_id"] == ZONAL_KEY_ID
    assert receipt["signature"]["algorithm"] == "HMAC-SHA256"
    assert receipt["signature"]["key_id"] == ZONAL_KEY_ID
    assert receipt["probability_raster_sha256"] == file_sha256(contract["raster_path"])
    assert receipt["authoritative_geometry_sha256"] == file_sha256(
        contract["geometry_path"]
    )

    areas = verify_zonal(receipt, contract)
    assert [area["subdistrict_id"] for area in areas] == ["AREA-A", "AREA-B"]
    assert areas[0]["sample_pixel_count"] == 511
    assert areas[0]["mean_flood_probability_0_1"] == pytest.approx(0.2)
    assert areas[0]["binary_flood_share_0_1"] == 0.0
    assert areas[1]["sample_pixel_count"] == 512
    assert areas[1]["mean_flood_probability_0_1"] == pytest.approx(0.8)
    assert areas[1]["binary_flood_share_0_1"] == 1.0
    assert areas[1]["estimated_flood_area_square_map_units"] == 51200.0

    areas[0]["subdistrict_name"] = "mutated copy"
    assert receipt["areas"][0]["subdistrict_name"] == "West"


def test_trusted_zonal_receipt_is_deterministic_canonical_and_path_private(
    tmp_path: Path,
) -> None:
    contract = zonal_contract(tmp_path)
    first = create_zonal(contract)
    second = create_zonal(contract)
    assert first == second

    reordered = dict(reversed(list(first.items())))
    assert verify_zonal(reordered, contract)[0]["subdistrict_id"] == "AREA-A"
    serialized = json.dumps(first, ensure_ascii=False)
    assert str(tmp_path) not in serialized
    assert str(contract["raster_path"]) not in serialized
    assert ZONAL_SIGNING_KEY.decode("ascii") not in serialized


@pytest.mark.parametrize("dataset_mode", ["fixture_demo", "candidate"])
def test_trusted_zonal_adapter_blocks_fixture_and_candidate_sources(
    tmp_path: Path, dataset_mode: str
) -> None:
    contract = zonal_contract(
        tmp_path,
        metadata_overrides={
            "dataset_mode": dataset_mode,
            "operational_status": "non_operational",
            "confidence_class": "low",
            "can_feed_decision_layer": False,
            "reason_blocked": "The source remains report-only.",
        },
    )
    contract["raster_receipt"] = probability_raster_receipt(
        contract["metadata"],
        probability_raster_sha256=file_sha256(contract["raster_path"]),
    )
    with pytest.raises(ProbabilityAggregationError, match="remain report-only"):
        create_zonal(contract)


@pytest.mark.parametrize(
    ("artifact", "message"),
    [
        ("raster", "Probability raster checksum"),
        ("geometry", "Authoritative geometry checksum"),
    ],
)
def test_trusted_zonal_adapter_rejects_artifact_substitution(
    tmp_path: Path, artifact: str, message: str
) -> None:
    contract = zonal_contract(tmp_path)
    path = contract[f"{artifact}_path"]
    path.write_bytes(path.read_bytes() + b"substituted")

    with pytest.raises(ProbabilityAggregationError, match=message):
        create_zonal(contract)


def test_trusted_zonal_adapter_rejects_geometry_feature_order_substitution(
    tmp_path: Path,
) -> None:
    contract = zonal_contract(tmp_path)
    document = json.loads(contract["geometry_path"].read_text(encoding="utf-8"))
    document["features"].reverse()
    contract["geometry_path"].write_text(
        json.dumps(document, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )

    with pytest.raises(ProbabilityAggregationError, match="geometry checksum"):
        create_zonal(contract)


def test_trusted_zonal_snapshot_defeats_substitute_read_restore_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = zonal_contract(tmp_path)
    raster_path = contract["raster_path"]
    original_bytes = raster_path.read_bytes()
    alternate_values = np.full((32, 32), 0.95, dtype=np.float32)
    alternate_path = write_probability_raster(
        tmp_path / "substitute.tif", values=alternate_values
    )
    alternate_bytes = alternate_path.read_bytes()
    actual_reader = trusted_zonal_module._read_probability_raster
    observed_snapshot: list[object] = []

    def substitute_while_parsing(
        source: object, *, expected_grid: dict[str, object]
    ) -> dict[str, object]:
        observed_snapshot.append(source)
        raster_path.write_bytes(alternate_bytes)
        try:
            return actual_reader(source, expected_grid=expected_grid)
        finally:
            raster_path.write_bytes(original_bytes)

    monkeypatch.setattr(
        trusted_zonal_module,
        "_read_probability_raster",
        substitute_while_parsing,
    )

    receipt = create_zonal(contract)
    areas = verify_zonal(receipt, contract)
    assert len(observed_snapshot) == 1
    assert observed_snapshot[0] != raster_path
    assert areas[0]["mean_flood_probability_0_1"] == pytest.approx(0.2)
    assert areas[1]["mean_flood_probability_0_1"] == pytest.approx(0.8)
    assert (
        receipt["probability_raster_sha256"]
        == hashlib.sha256(original_bytes).hexdigest()
    )
    assert raster_path.read_bytes() == original_bytes


def test_trusted_zonal_geometry_buffer_defeats_substitute_read_restore_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = zonal_contract(tmp_path)
    geometry_path = contract["geometry_path"]
    original_bytes = geometry_path.read_bytes()
    substitute_features = default_area_features()
    substitute_features[0]["properties"]["ADM_NAME"] = "Substitute East"
    substitute_features[1]["properties"]["ADM_NAME"] = "Substitute West"
    substitute_path = write_area_geojson(
        tmp_path / "substitute.geojson", features=substitute_features
    )
    substitute_bytes = substitute_path.read_bytes()
    actual_reader = trusted_zonal_module._read_authoritative_geojson_snapshot
    observed_buffers: list[bytes] = []

    def substitute_while_parsing(
        document_bytes: bytes, **kwargs: object
    ) -> dict[str, object]:
        observed_buffers.append(document_bytes)
        geometry_path.write_bytes(substitute_bytes)
        try:
            return actual_reader(document_bytes, **kwargs)
        finally:
            geometry_path.write_bytes(original_bytes)

    monkeypatch.setattr(
        trusted_zonal_module,
        "_read_authoritative_geojson_snapshot",
        substitute_while_parsing,
    )

    receipt = create_zonal(contract)
    areas = verify_zonal(receipt, contract)
    assert observed_buffers == [original_bytes]
    assert [area["subdistrict_name"] for area in areas] == ["West", "East"]
    assert (
        receipt["authoritative_geometry_sha256"]
        == hashlib.sha256(original_bytes).hexdigest()
    )
    assert geometry_path.read_bytes() == original_bytes


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("crs", "file CRS"),
        ("transform", "file transform"),
        ("shape", "file width"),
        ("dtype", "file dtypes"),
        ("description", "file descriptions"),
    ],
)
def test_trusted_zonal_adapter_binds_actual_raster_grid(
    tmp_path: Path, mutation: str, message: str
) -> None:
    values = None
    crs = "EPSG:32647"
    transform: object | None = None
    dtype = "float32"
    description = "flood_probability_0_1"
    if mutation == "crs":
        crs = "EPSG:32648"
    elif mutation == "transform":
        transform = from_origin(600010.0, 2200320.0, 10.0, 10.0)
    elif mutation == "shape":
        values = np.full((32, 31), 0.4, dtype=np.float32)
    elif mutation == "dtype":
        dtype = "int16"
    elif mutation == "description":
        description = "class_1"
    contract = zonal_contract(
        tmp_path,
        raster_values=values,
        raster_crs=crs,
        raster_transform=transform,
        raster_dtype=dtype,
        raster_description=description,
    )

    with pytest.raises(ProbabilityAggregationError, match=message):
        create_zonal(contract)


@pytest.mark.parametrize(
    ("invalid", "message"),
    [
        (np.float32(1.01), r"within \[0, 1\]"),
        (np.float32(-0.01), r"within \[0, 1\]"),
        (np.float32(np.nan), "non-finite"),
        (np.float32(np.inf), "non-finite"),
    ],
)
def test_trusted_zonal_adapter_rejects_invalid_probability_values(
    tmp_path: Path, invalid: np.float32, message: str
) -> None:
    values = np.full((32, 32), 0.4, dtype=np.float32)
    values[5, 5] = invalid
    contract = zonal_contract(tmp_path, raster_values=values)

    with pytest.raises(ProbabilityAggregationError, match=message):
        create_zonal(contract)


def test_trusted_zonal_adapter_requires_nodata_outside_probability_domain(
    tmp_path: Path,
) -> None:
    values = np.full((32, 32), 0.4, dtype=np.float32)
    contract = zonal_contract(tmp_path, raster_values=values)
    write_probability_raster(contract["raster_path"], values=values, nodata=0.0)
    raster_receipt = probability_raster_receipt(
        contract["metadata"],
        probability_raster_sha256=file_sha256(contract["raster_path"]),
    )
    raster_receipt["grid"]["nodata"] = 0.0
    contract["raster_receipt"] = raster_receipt

    with pytest.raises(ProbabilityAggregationError, match="outside.*probability range"):
        create_zonal(contract)


def test_trusted_zonal_adapter_rejects_unbound_internal_raster_mask(
    tmp_path: Path,
) -> None:
    contract = zonal_contract(tmp_path)
    mask = np.full((32, 32), 255, dtype=np.uint8)
    mask[0, 0] = 0
    mask[2, 2] = 0
    with rasterio.open(contract["raster_path"], "r+") as dataset:
        dataset.write_mask(mask)
    contract["raster_receipt"] = probability_raster_receipt(
        contract["metadata"],
        probability_raster_sha256=file_sha256(contract["raster_path"]),
    )

    with pytest.raises(ProbabilityAggregationError, match="internal mask"):
        create_zonal(contract)


@pytest.mark.parametrize(
    ("features", "geometry_crs", "overrides", "message"),
    [
        (default_area_features(), None, {}, "explicit named CRS"),
        (default_area_features(), "EPSG:32647", {"crs": "EPSG:4326"}, "CRS"),
        (
            [default_area_features()[0], deepcopy(default_area_features()[0])],
            "EPSG:32647",
            {},
            "area IDs must be unique",
        ),
        (
            [
                default_area_features()[0],
                {
                    "type": "Feature",
                    "properties": {"ADM_ID": "AREA-A", "ADM_NAME": "Invalid"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [600000.0, 2200000.0],
                                [600160.0, 2200320.0],
                                [600000.0, 2200320.0],
                                [600160.0, 2200000.0],
                                [600000.0, 2200000.0],
                            ]
                        ],
                    },
                },
            ],
            "EPSG:32647",
            {},
            "valid non-empty polygon",
        ),
        (
            [
                default_area_features()[0],
                {
                    "type": "Feature",
                    "properties": {"ADM_ID": "AREA-A", "ADM_NAME": "Away"},
                    "geometry": polygon_geometry(1.0, 1.0, 2.0, 2.0),
                },
            ],
            "EPSG:32647",
            {},
            "no areal overlap",
        ),
        (
            [
                default_area_features()[0],
                {
                    "type": "Feature",
                    "properties": {"ADM_ID": "AREA-A", "ADM_NAME": "Overlap"},
                    "geometry": polygon_geometry(
                        600150.0, 2200000.0, 600250.0, 2200320.0
                    ),
                },
            ],
            "EPSG:32647",
            {},
            "must not overlap",
        ),
    ],
)
def test_trusted_zonal_adapter_rejects_untrusted_or_invalid_geometry(
    tmp_path: Path,
    features: list[dict[str, object]],
    geometry_crs: str | None,
    overrides: dict[str, object],
    message: str,
) -> None:
    contract = zonal_contract(
        tmp_path,
        features=features,
        geometry_crs=geometry_crs,
        geometry_overrides=overrides,
    )

    with pytest.raises(ProbabilityAggregationError, match=message):
        create_zonal(contract)


def test_trusted_zonal_adapter_reprojects_explicit_authoritative_geometry(
    tmp_path: Path,
) -> None:
    wgs84_features = deepcopy(default_area_features())
    for feature in wgs84_features:
        feature["geometry"] = transform_geom(
            "EPSG:32647", "EPSG:4326", feature["geometry"], precision=12
        )
    contract = zonal_contract(
        tmp_path,
        features=wgs84_features,
        geometry_crs="EPSG:4326",
        geometry_overrides={"crs": "EPSG:4326"},
    )

    receipt = create_zonal(contract)
    areas = verify_zonal(receipt, contract)
    assert [area["subdistrict_id"] for area in areas] == ["AREA-A", "AREA-B"]
    assert receipt["authoritative_geometry"]["crs"] == "EPSG:4326"


def test_trusted_zonal_adapter_rejects_area_without_valid_pixel_centres(
    tmp_path: Path,
) -> None:
    features = [
        default_area_features()[0],
        {
            "type": "Feature",
            "properties": {"ADM_ID": "AREA-A", "ADM_NAME": "Too narrow"},
            "geometry": polygon_geometry(600000.0, 2200000.0, 600001.0, 2200320.0),
        },
    ]
    contract = zonal_contract(tmp_path, features=features)

    with pytest.raises(ProbabilityAggregationError, match="no valid probability"):
        create_zonal(contract)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"feature_count": 3}, "feature count"),
        ({"authority_status": "candidate"}, "authority_status"),
        ({"processing_allowed": False}, "processing_allowed"),
        ({"area_id_field": "ADM_NAME", "area_name_field": "ADM_NAME"}, "distinct"),
        ({"source_name": r"C:\Users\private\areas.geojson"}, "private path"),
        ({"dataset_id": "/etc/private-area-source"}, "private path"),
    ],
)
def test_trusted_zonal_adapter_validates_authoritative_geometry_lineage(
    tmp_path: Path, overrides: dict[str, object], message: str
) -> None:
    contract = zonal_contract(tmp_path, geometry_overrides=overrides)

    with pytest.raises(ProbabilityAggregationError, match=message):
        create_zonal(contract)


def test_trusted_zonal_adapter_rejects_receipt_timestamp_before_lineage(
    tmp_path: Path,
) -> None:
    contract = zonal_contract(tmp_path)
    with pytest.raises(ProbabilityAggregationError, match="cannot predate"):
        create_zonal(contract, generated_at="2024-09-15T23:30:00Z")

    contract["geometry_receipt"]["source_timestamp"] = "2024-09-17T00:00:00Z"
    with pytest.raises(ProbabilityAggregationError, match="cannot predate"):
        create_zonal(contract)


def test_trusted_zonal_adapter_rejects_private_path_in_area_properties(
    tmp_path: Path,
) -> None:
    features = default_area_features()
    features[0]["properties"]["ADM_NAME"] = "/tmp/private/area.geojson"
    contract = zonal_contract(tmp_path, features=features)

    with pytest.raises(ProbabilityAggregationError, match="private path"):
        create_zonal(contract)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("area", "signature is invalid"),
        ("raster_sha", "signature is invalid"),
        ("geometry_sha", "signature is invalid"),
        ("grid", "signature is invalid"),
        ("generated_at", "signature is invalid"),
    ],
)
def test_signed_zonal_receipt_rejects_unsigned_mutation(
    tmp_path: Path, mutation: str, message: str
) -> None:
    contract = zonal_contract(tmp_path)
    receipt = create_zonal(contract)
    if mutation == "area":
        receipt["areas"][0]["mean_flood_probability_0_1"] = 0.99
    elif mutation == "raster_sha":
        receipt["probability_raster_sha256"] = "0" * 64
    elif mutation == "geometry_sha":
        receipt["authoritative_geometry_sha256"] = "0" * 64
    elif mutation == "grid":
        receipt["probability_grid"]["width"] = 31
    elif mutation == "generated_at":
        receipt["generated_at"] = "2024-09-17T00:00:00Z"

    with pytest.raises(ProbabilityAggregationError, match=message):
        verify_zonal(receipt, contract)


def test_signed_zonal_receipt_rejects_wrong_key_and_key_id(tmp_path: Path) -> None:
    contract = zonal_contract(tmp_path)
    receipt = create_zonal(contract)

    with pytest.raises(ProbabilityAggregationError, match="signature is invalid"):
        verify_zonal(receipt, contract, signing_key=b"x" * 32)
    with pytest.raises(ProbabilityAggregationError, match="at least 32 bytes"):
        verify_zonal(receipt, contract, signing_key=b"short")
    with pytest.raises(ProbabilityAggregationError, match="external bytes"):
        verify_zonal(receipt, contract, signing_key=None)
    with pytest.raises(ProbabilityAggregationError, match="key ID is not trusted"):
        verify_zonal(receipt, contract, expected_key_id="test/other-key")

    receipt["signature"]["key_id"] = "test/other-key"
    with pytest.raises(ProbabilityAggregationError, match="signed key ID"):
        verify_zonal(receipt, contract)

    receipt["key_id"] = "test/other-key"
    with pytest.raises(ProbabilityAggregationError, match="signature is invalid"):
        verify_zonal(receipt, contract, expected_key_id="test/other-key")


@pytest.mark.parametrize("field", ["signature", "key_id", "areas", "probability_grid"])
def test_signed_zonal_receipt_rejects_missing_required_fields(
    tmp_path: Path, field: str
) -> None:
    contract = zonal_contract(tmp_path)
    receipt = create_zonal(contract)
    del receipt[field]

    with pytest.raises(ProbabilityAggregationError, match="missing required fields"):
        verify_zonal(receipt, contract)


def test_signed_zonal_receipt_rejects_unsupported_fields(tmp_path: Path) -> None:
    contract = zonal_contract(tmp_path)
    receipt = create_zonal(contract)
    receipt["private_path"] = str(tmp_path)

    with pytest.raises(ProbabilityAggregationError, match="unsupported fields"):
        verify_zonal(receipt, contract)


def test_signed_zonal_receipt_rejects_unsupported_signature_algorithm(
    tmp_path: Path,
) -> None:
    contract = zonal_contract(tmp_path)
    receipt = create_zonal(contract)
    receipt["signature"]["algorithm"] = "SHA256"

    with pytest.raises(ProbabilityAggregationError, match="HMAC-SHA256"):
        verify_zonal(receipt, contract)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("share", "binary share"),
        ("sample_area", "sampled area"),
        ("flood_area", "estimated flood area"),
        ("threshold", "probability threshold"),
        ("eligibility", "not marked"),
        ("order", "ascending order"),
    ],
)
def test_signed_zonal_receipt_rejects_resigned_inconsistent_statistics(
    tmp_path: Path, mutation: str, message: str
) -> None:
    contract = zonal_contract(tmp_path)
    receipt = create_zonal(contract)
    if mutation == "share":
        receipt["areas"][0]["binary_flood_share_0_1"] = 0.5
    elif mutation == "sample_area":
        receipt["areas"][0]["sampled_area_square_map_units"] = 1.0
    elif mutation == "flood_area":
        receipt["areas"][1]["estimated_flood_area_square_map_units"] = 1.0
    elif mutation == "threshold":
        receipt["areas"][0]["probability_threshold"] = 0.6
    elif mutation == "eligibility":
        receipt["areas"][0]["eligible_for_fpps"] = False
    elif mutation == "order":
        receipt["areas"].reverse()
    resign_zonal(receipt)

    with pytest.raises(ProbabilityAggregationError, match=message):
        verify_zonal(receipt, contract)


def test_signed_zonal_receipt_rejects_lineage_substitution_after_valid_signature(
    tmp_path: Path,
) -> None:
    contract = zonal_contract(tmp_path)
    receipt = create_zonal(contract)

    changed_geometry = deepcopy(contract["geometry_receipt"])
    changed_geometry["data_version"] = "substituted-version"
    with pytest.raises(ProbabilityAggregationError, match="geometry_receipt_sha256"):
        verify_zonal(
            receipt,
            contract,
            authoritative_geometry_receipt=changed_geometry,
        )

    changed_metadata = deepcopy(contract["metadata"])
    changed_metadata["model_revision"] = "substituted-model"
    changed_raster_receipt = probability_raster_receipt(
        changed_metadata,
        probability_raster_sha256=file_sha256(contract["raster_path"]),
    )
    with pytest.raises(ProbabilityAggregationError, match="model_revision"):
        verify_zonal(
            receipt,
            contract,
            source_metadata=changed_metadata,
            probability_raster_receipt=changed_raster_receipt,
        )


def test_trusted_zonal_errors_and_receipts_do_not_disclose_private_paths(
    tmp_path: Path,
) -> None:
    contract = zonal_contract(tmp_path)
    contract["geometry_path"].write_text("not-json", encoding="utf-8")
    contract["geometry_receipt"]["sha256"] = file_sha256(contract["geometry_path"])

    with pytest.raises(ProbabilityAggregationError) as caught:
        create_zonal(contract)
    assert str(tmp_path) not in str(caught.value)


def test_trusted_zonal_signing_contract_rejects_weak_or_invalid_keys(
    tmp_path: Path,
) -> None:
    contract = zonal_contract(tmp_path)
    with pytest.raises(ProbabilityAggregationError, match="at least 32 bytes"):
        create_zonal(contract, signing_key=b"short")
    with pytest.raises(ProbabilityAggregationError, match="external bytes"):
        create_zonal(contract, signing_key="not-bytes")
    with pytest.raises(ProbabilityAggregationError, match="external bytes"):
        create_zonal(contract, signing_key=None)
    with pytest.raises(ProbabilityAggregationError, match="private path"):
        create_zonal(contract, key_id=r"C:\Users\private\secret.key")


def zonal_cli_arguments(
    contract: dict[str, object], tmp_path: Path, output: Path
) -> list[str]:
    manifest_path = tmp_path / "model-run.json"
    raster_receipt_path = tmp_path / "probability-raster-receipt.json"
    geometry_receipt_path = tmp_path / "geometry-receipt.json"
    for path, document in (
        (manifest_path, contract["metadata"]),
        (raster_receipt_path, contract["raster_receipt"]),
        (geometry_receipt_path, contract["geometry_receipt"]),
    ):
        path.write_text(
            json.dumps(document, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )
    return [
        "--probability-raster",
        str(contract["raster_path"]),
        "--authoritative-geometry",
        str(contract["geometry_path"]),
        "--model-run-manifest",
        str(manifest_path),
        "--probability-raster-receipt",
        str(raster_receipt_path),
        "--authoritative-geometry-receipt",
        str(geometry_receipt_path),
        "--output",
        str(output),
        "--key-id",
        ZONAL_KEY_ID,
        "--generated-at",
        ZONAL_GENERATED_AT,
    ]


def test_trusted_zonal_cli_writes_exclusive_canonical_external_receipt(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    contract = zonal_contract(tmp_path)
    output = tmp_path / "trusted-zonal-receipt.json"
    arguments = zonal_cli_arguments(contract, tmp_path, output)
    environment = {"FLOODGUARD_ZONAL_SIGNING_KEY_HEX": ZONAL_SIGNING_KEY.hex()}

    assert zonal_cli_main(arguments, environ=environment) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "trusted_zonal_receipt_written" in captured.out
    assert str(tmp_path) not in captured.out
    assert ZONAL_SIGNING_KEY.hex() not in captured.out
    serialized = output.read_text(encoding="utf-8")
    assert serialized.endswith("\n")
    assert (
        serialized
        == json.dumps(
            json.loads(serialized),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
    receipt = json.loads(serialized)
    assert verify_zonal(receipt, contract)[0]["subdistrict_id"] == "AREA-A"
    assert str(tmp_path) not in serialized
    assert ZONAL_SIGNING_KEY.hex() not in serialized

    before = output.read_bytes()
    assert zonal_cli_main(arguments, environ=environment) == 2
    captured = capsys.readouterr()
    assert "never overwritten" in captured.err
    assert str(tmp_path) not in captured.err
    assert output.read_bytes() == before


def test_trusted_zonal_cli_requires_external_environment_key_without_leakage(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    contract = zonal_contract(tmp_path)
    output = tmp_path / "missing-key.json"
    arguments = zonal_cli_arguments(contract, tmp_path, output)

    assert zonal_cli_main(arguments, environ={}) == 2
    captured = capsys.readouterr()
    assert "absent or empty" in captured.err
    assert str(tmp_path) not in captured.err
    assert not output.exists()

    assert (
        zonal_cli_main(
            arguments,
            environ={"FLOODGUARD_ZONAL_SIGNING_KEY_HEX": "00" * 16},
        )
        == 2
    )
    captured = capsys.readouterr()
    assert "at least 32 bytes" in captured.err
    assert "00" * 16 not in captured.err
    assert not output.exists()


def test_trusted_zonal_cli_rejects_repository_internal_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    contract = zonal_contract(tmp_path)
    output = ROOT / f"zonal-cli-must-not-write-{tmp_path.name}.json"
    assert not output.exists()
    arguments = zonal_cli_arguments(contract, tmp_path, output)
    environment = {"FLOODGUARD_ZONAL_SIGNING_KEY_HEX": ZONAL_SIGNING_KEY.hex()}

    assert zonal_cli_main(arguments, environ=environment) == 2
    captured = capsys.readouterr()
    assert "outside the FloodGuard repository" in captured.err
    assert str(output) not in captured.err
    assert not output.exists()


def test_trusted_zonal_cli_snapshots_all_receipts_before_coordinated_substitution(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = zonal_contract(tmp_path)
    output = tmp_path / "coordinated-race-receipt.json"
    arguments = zonal_cli_arguments(contract, tmp_path, output)
    environment = {"FLOODGUARD_ZONAL_SIGNING_KEY_HEX": ZONAL_SIGNING_KEY.hex()}
    paths = {
        "model-run manifest": tmp_path / "model-run.json",
        "probability-raster receipt": tmp_path / "probability-raster-receipt.json",
        "authoritative-geometry receipt": tmp_path / "geometry-receipt.json",
    }
    originals = {label: path.read_bytes() for label, path in paths.items()}
    alternate_metadata = deepcopy(contract["metadata"])
    alternate_metadata["model_revision"] = "transient-substitute-model"
    alternate_raster_receipt = probability_raster_receipt(
        alternate_metadata,
        probability_raster_sha256=file_sha256(contract["raster_path"]),
    )
    alternate_geometry_receipt = deepcopy(contract["geometry_receipt"])
    alternate_geometry_receipt["data_version"] = "transient-substitute-geometry"
    alternates = {
        "model-run manifest": json.dumps(
            alternate_metadata, ensure_ascii=False, sort_keys=True
        ).encode("utf-8"),
        "probability-raster receipt": json.dumps(
            alternate_raster_receipt, ensure_ascii=False, sort_keys=True
        ).encode("utf-8"),
        "authoritative-geometry receipt": json.dumps(
            alternate_geometry_receipt, ensure_ascii=False, sort_keys=True
        ).encode("utf-8"),
    }
    actual_parser = trusted_zonal_cli_module._parse_json_snapshot
    parsed_snapshot_hashes: dict[str, str] = {}

    def substitute_all_paths_while_parsing(content: bytes, label: str) -> object:
        parsed_snapshot_hashes[label] = hashlib.sha256(content).hexdigest()
        for receipt_label, path in paths.items():
            path.write_bytes(alternates[receipt_label])
        try:
            return actual_parser(content, label)
        finally:
            for receipt_label, path in paths.items():
                path.write_bytes(originals[receipt_label])

    monkeypatch.setattr(
        trusted_zonal_cli_module,
        "_parse_json_snapshot",
        substitute_all_paths_while_parsing,
    )

    assert zonal_cli_main(arguments, environ=environment) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert parsed_snapshot_hashes == {
        label: hashlib.sha256(content).hexdigest()
        for label, content in originals.items()
    }
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["model_revision"] == "contract-proof-1"
    assert receipt["authoritative_geometry"]["data_version"] == "2024-09-reviewed"
    assert "transient-substitute" not in json.dumps(receipt, ensure_ascii=False)
    assert verify_zonal(receipt, contract)[0]["subdistrict_id"] == "AREA-A"
    assert {label: path.read_bytes() for label, path in paths.items()} == originals


def test_trusted_zonal_cli_rejects_detected_mid_read_receipt_mutation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = zonal_contract(tmp_path)
    output = tmp_path / "mid-read-mutation.json"
    arguments = zonal_cli_arguments(contract, tmp_path, output)
    environment = {"FLOODGUARD_ZONAL_SIGNING_KEY_HEX": ZONAL_SIGNING_KEY.hex()}
    actual_state = trusted_zonal_module._descriptor_state
    calls = 0

    def mutated_descriptor_state(stream: object) -> tuple[int, int, int, int, int]:
        nonlocal calls
        calls += 1
        state = actual_state(stream)
        if calls == 2:
            return (*state[:-1], state[-1] + 1)
        return state

    monkeypatch.setattr(
        trusted_zonal_module,
        "_descriptor_state",
        mutated_descriptor_state,
    )

    assert zonal_cli_main(arguments, environ=environment) == 2
    captured = capsys.readouterr()
    assert "changed while its byte snapshot was read" in captured.err
    assert str(tmp_path) not in captured.err
    assert ZONAL_SIGNING_KEY.hex() not in captured.err
    assert not output.exists()


def test_trusted_zonal_cli_rejects_private_paths_inside_receipt_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    contract = zonal_contract(tmp_path)
    output = tmp_path / "private-path-receipt.json"
    arguments = zonal_cli_arguments(contract, tmp_path, output)
    private_manifest = deepcopy(contract["metadata"])
    private_path = r"C:\Users\private\model-output.tif"
    private_manifest["source_name"] = private_path
    (tmp_path / "model-run.json").write_text(
        json.dumps(private_manifest, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    environment = {"FLOODGUARD_ZONAL_SIGNING_KEY_HEX": ZONAL_SIGNING_KEY.hex()}

    assert zonal_cli_main(arguments, environ=environment) == 2
    captured = capsys.readouterr()
    assert "private absolute paths" in captured.err
    assert private_path not in captured.err
    assert str(tmp_path) not in captured.err
    assert not output.exists()


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b'{"run_id":"first","run_id":"second"}', "duplicate keys"),
        (b'{"metric":NaN}', "non-finite"),
    ],
)
def test_trusted_zonal_cli_rejects_ambiguous_json_snapshots(
    content: bytes, message: str
) -> None:
    with pytest.raises(trusted_zonal_cli_module.TrustedZonalCliError, match=message):
        trusted_zonal_cli_module._parse_json_snapshot(content, "test receipt")
