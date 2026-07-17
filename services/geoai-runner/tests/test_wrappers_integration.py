from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import rasterio
from floodguard.probability_aggregation import aggregate_probability_cells
from rasterio.windows import Window

from geoai_runner.infer import (
    OUTPUT_NODATA,
    VerifiedLoadedModel,
    class1_probability_from_logits,
    run_prediction,
)
from geoai_runner.prepare import (
    TileExportReceipt,
    TileMembership,
    export_training_tiles,
    validate_prepared_inputs,
    write_prepared_tile_manifest,
)
from geoai_runner.proposal_evidence import (
    validate_proposal_proof_receipt,
    write_proposal_proof_artifacts,
)
from geoai_runner.train import train_segmentation_candidate
from geoai_runner.validate import RasterValidationError

from .helpers import build_synthetic_workspace, sha256


def test_export_wrapper_validates_then_calls_geoai_signature(tmp_path: Path) -> None:
    evidence = build_synthetic_workspace(tmp_path)
    calls: dict[str, Any] = {}

    def exporter(*args: Any, **kwargs: Any) -> None:
        calls["args"] = args
        calls["kwargs"] = kwargs
        with rasterio.open(kwargs["in_class_data"]) as export_mask:
            calls["export_mask_classes"] = set(np.unique(export_mask.read(1)).tolist())
            calls["export_mask_nodata"] = export_mask.nodata
        _write_tile_pair(
            evidence,
            Path(args[1]) / "images" / "tile_000001.tif",
            Path(args[1]) / "labels" / "tile_000001.tif",
            column_offset=0,
        )

    output = evidence["workspace"] / "tiles"
    receipt = export_training_tiles(
        evidence["contract"],
        evidence["encoded"],
        evidence["mask"],
        evidence["sidecar"],
        output,
        exporter=exporter,
    )
    assert receipt.grid.count == 8
    assert receipt.training_tile_count == 1
    assert receipt.holdout_tile_count == 0
    assert receipt.rejected_boundary_tile_count == 0
    assert len(receipt.prepared_manifest_sha256) == 64
    assert calls["args"] == (str(evidence["encoded"].resolve()), str(output.resolve()))
    assert calls["kwargs"]["in_class_data"].endswith(".floodguard-geoai-export-mask.tif")
    assert not Path(calls["kwargs"]["in_class_data"]).exists()
    assert calls["export_mask_classes"] == {0, 1}
    assert calls["export_mask_nodata"] is None
    assert calls["kwargs"]["tile_size"] == 4
    assert calls["kwargs"]["stride"] == 3
    assert calls["kwargs"]["apply_augmentation"] is False


def test_export_restores_geoai_omitted_label_nodata_after_value_validation(
    tmp_path: Path,
) -> None:
    evidence = build_synthetic_workspace(tmp_path)

    def exporter(*args: Any, **_: Any) -> None:
        _write_tile_pair(
            evidence,
            Path(args[1]) / "images" / "tile_000001.tif",
            Path(args[1]) / "labels" / "tile_000001.tif",
            column_offset=0,
            preserve_label_nodata=False,
        )

    output = evidence["workspace"] / "geoai-profile-normalization"
    export_training_tiles(
        evidence["contract"],
        evidence["encoded"],
        evidence["mask"],
        evidence["sidecar"],
        output,
        exporter=exporter,
    )

    with rasterio.open(output / "labels" / "tile_000001.tif") as label:
        assert label.nodata == 255
        assert set(np.unique(label.read(1)).tolist()).issubset({0, 1, 255})


def test_export_partitions_training_holdout_and_boundary_tiles_before_manifest(
    tmp_path: Path,
) -> None:
    evidence = build_synthetic_workspace(tmp_path)

    def exporter(*args: Any, **_: Any) -> None:
        output = Path(args[1])
        for name, offset in (("train", 0), ("holdout", 4), ("boundary", 3)):
            _write_tile_pair(
                evidence,
                output / "images" / f"{name}.tif",
                output / "labels" / f"{name}.tif",
                column_offset=offset,
            )

    output = evidence["workspace"] / "partitioned-tiles"
    receipt = export_training_tiles(
        evidence["contract"],
        evidence["encoded"],
        evidence["mask"],
        evidence["sidecar"],
        output,
        exporter=exporter,
    )
    assert receipt.training_tile_count == 1
    assert receipt.holdout_tile_count == 1
    assert receipt.rejected_boundary_tile_count == 1
    assert sorted(path.name for path in (output / "images").glob("*.tif")) == ["train.tif"]
    assert (output / "holdout" / "images" / "holdout.tif").is_file()
    assert (output / "rejected-boundary" / "images" / "boundary.tif").is_file()
    manifest = json.loads(
        (output / receipt.prepared_manifest_relative_path).read_text(encoding="utf-8")
    )
    assert [row["spatial_group_id"] for row in manifest["tiles"]] == ["train-zone-01"]


@pytest.mark.parametrize(
    ("artifact", "message"),
    [
        ("encoded", "Encoded feature checksum"),
        ("mask", "Reference mask checksum"),
    ],
)
def test_export_rehashes_previously_validated_inputs_before_geoai(
    tmp_path: Path,
    artifact: str,
    message: str,
) -> None:
    evidence = build_synthetic_workspace(tmp_path)
    validate_prepared_inputs(
        evidence["contract"],
        evidence["encoded"],
        evidence["mask"],
        evidence["sidecar"],
    )
    path = evidence[artifact]
    with rasterio.open(path, "r+") as raster:
        values = raster.read(1)
        values[0, 0] = 1 if values[0, 0] == 0 else 0
        raster.write(values, 1)
    called = False

    def exporter(*_: Any, **__: Any) -> None:
        nonlocal called
        called = True

    with pytest.raises(ValueError, match=message):
        export_training_tiles(
            evidence["contract"],
            evidence["encoded"],
            evidence["mask"],
            evidence["sidecar"],
            evidence["workspace"] / "mutated-tiles",
            exporter=exporter,
        )
    assert called is False


def test_export_rehashes_transform_sidecar_before_geoai(tmp_path: Path) -> None:
    evidence = build_synthetic_workspace(tmp_path)
    evidence["sidecar"].write_text(
        evidence["sidecar"].read_text(encoding="utf-8") + " ",
        encoding="utf-8",
    )
    called = False

    def exporter(*_: Any, **__: Any) -> None:
        nonlocal called
        called = True

    with pytest.raises(ValueError, match="sidecar checksum"):
        export_training_tiles(
            evidence["contract"],
            evidence["encoded"],
            evidence["mask"],
            evidence["sidecar"],
            evidence["workspace"] / "tampered-sidecar-tiles",
            exporter=exporter,
        )
    assert called is False


def test_export_and_training_are_blocked_before_lazy_geoai_import(tmp_path: Path) -> None:
    evidence = build_synthetic_workspace(tmp_path)
    blocked = replace(
        evidence["contract"],
        run_status="blocked",
        processing_allowed=False,
        input_manifest_rows=tuple(
            replace(row, processing_allowed=False)
            for row in evidence["contract"].input_manifest_rows
        ),
        spatial_holdout_ids=(),
        spatial_partitions=(),
    )
    blocked.validate()
    with pytest.raises(PermissionError, match="blocks processing"):
        export_training_tiles(
            blocked,
            evidence["encoded"],
            evidence["mask"],
            evidence["sidecar"],
            evidence["workspace"] / "blocked-tiles",
        )
    assert "geoai" not in sys.modules


def test_runner_operations_require_their_bound_contract_stage(tmp_path: Path) -> None:
    evidence = build_synthetic_workspace(tmp_path)
    with pytest.raises(ValueError, match="unprepared contract"):
        export_training_tiles(
            evidence["inference_contract"],
            evidence["encoded"],
            evidence["mask"],
            evidence["sidecar"],
            evidence["workspace"] / "wrong-stage-export",
            exporter=lambda *_args, **_kwargs: pytest.fail("exporter must not be called"),
        )
    with pytest.raises(ValueError, match="prepared or running"):
        train_segmentation_candidate(
            evidence["contract"],
            evidence["workspace"] / "missing-images",
            evidence["workspace"] / "missing-labels",
            evidence["workspace"] / "wrong-stage-training",
            prepared_manifest_path=evidence["workspace"] / "missing-manifest.json",
            sidecar_path=evidence["sidecar"],
            trainer=lambda **_kwargs: pytest.fail("trainer must not be called"),
        )
    with pytest.raises(ValueError, match="completed run contract"):
        run_prediction(
            evidence["contract"],
            encoded_feature_path=evidence["encoded"],
            sidecar_path=evidence["sidecar"],
            checkpoint_path=evidence["checkpoint"],
            output_path=evidence["probability"],
            prepared_manifest_path=evidence["lineage_manifest"],
            model_loader=lambda **_kwargs: pytest.fail("loader must not be called"),
            predictor=lambda **_kwargs: pytest.fail("predictor must not be called"),
        )


def test_training_wrapper_requires_bound_membership_and_uses_none_weights(
    tmp_path: Path,
) -> None:
    evidence = build_synthetic_workspace(tmp_path)
    images = evidence["workspace"] / "tiles" / "images"
    labels = evidence["workspace"] / "tiles" / "labels"
    _write_tile_pair(
        evidence,
        images / "arbitrary-image-name.tif",
        labels / "arbitrary-label-name.tif",
        column_offset=0,
    )
    manifest = evidence["workspace"] / "tiles" / "prepared-manifest.json"
    manifest_sha256 = write_prepared_tile_manifest(
        evidence["contract"],
        images,
        labels,
        (
            TileMembership(
                image_path="arbitrary-image-name.tif",
                label_path="arbitrary-label-name.tif",
            ),
        ),
        manifest,
    )
    training_contract = replace(
        evidence["contract"],
        run_status="running",
        prepared_tile_manifest_sha256=manifest_sha256,
    )
    training_contract.validate()
    calls: dict[str, Any] = {}

    def trainer(**kwargs: Any) -> dict[str, str]:
        calls.update(kwargs)
        (Path(kwargs["output_dir"]) / "best_model.pth").write_bytes(b"raw state")
        return {"checkpoint": "synthetic"}

    def checkpoint_loader(_: Path) -> dict[str, str]:
        return {"synthetic_weight": "state"}

    def checkpoint_saver(payload: dict[str, Any], path: Path) -> None:
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    result = train_segmentation_candidate(
        training_contract,
        images,
        labels,
        evidence["workspace"] / "training-output",
        prepared_manifest_path=manifest,
        sidecar_path=evidence["sidecar"],
        trainer=trainer,
        checkpoint_loader=checkpoint_loader,
        checkpoint_saver=checkpoint_saver,
        epochs=2,
    )
    assert result.trainer_result == {"checkpoint": "synthetic"}
    assert result.packaged_checkpoint_path.is_file()
    assert len(result.packaged_checkpoint_sha256) == 64
    envelope = json.loads(result.packaged_checkpoint_path.read_text(encoding="utf-8"))
    assert envelope["floodguard_checkpoint_schema"] == "1.1"
    assert envelope["model_revision"] == training_contract.model_revision
    assert envelope["architecture"] == training_contract.architecture
    assert envelope["source_state_sha256"] == result.raw_state_sha256
    assert _lineage_receipts(envelope) == training_contract.training_lineage_receipts()
    assert calls["architecture"] == "unet"
    assert calls["encoder_weights"] is None
    assert calls["num_channels"] == 8
    assert calls["num_classes"] == 2
    assert calls["ignore_index"] == 255
    assert calls["num_epochs"] == 2
    assert calls["seed"] == 42
    with rasterio.open(labels / "arbitrary-label-name.tif") as label:
        label_values = set(np.unique(label.read(1)).tolist())
        assert label.nodata == 255
    assert label_values.issubset({0, 1, 255})
    assert 255 in label_values

    inference_contract = replace(
        training_contract,
        run_status="completed",
        model_sha256=result.packaged_checkpoint_sha256,
    )
    packaged_model = object()

    def packaged_loader(**kwargs: Any) -> VerifiedLoadedModel:
        packaged = json.loads(Path(kwargs["checkpoint_path"]).read_text(encoding="utf-8"))
        assert packaged["model_revision"] == kwargs["model_revision"]
        assert packaged["architecture"] == kwargs["architecture"]
        return VerifiedLoadedModel(
            model=packaged_model,
            checkpoint_sha256=kwargs["checkpoint_sha256"],
            model_revision=kwargs["model_revision"],
            architecture=kwargs["architecture"],
            encoder=kwargs["encoder"],
            channel_count=kwargs["channel_count"],
            **_lineage_receipts(packaged),
        )

    def predictor(**kwargs: Any) -> None:
        assert kwargs["model"] is packaged_model
        with rasterio.open(kwargs["input_raster"]) as source:
            profile = source.profile.copy()
            values = np.full((1, source.height, source.width), 0.5, dtype=np.float32)
        profile.update(count=1, dtype="float32", nodata=kwargs["output_nodata"])
        with rasterio.open(kwargs["output_raster"], "w", **profile) as output:
            output.write(values)

    inference_grid = run_prediction(
        inference_contract,
        encoded_feature_path=evidence["encoded"],
        sidecar_path=evidence["sidecar"],
        checkpoint_path=result.packaged_checkpoint_path,
        output_path=evidence["probability"],
        prepared_manifest_path=manifest,
        model_loader=packaged_loader,
        predictor=predictor,
    )
    assert inference_grid.descriptions == ("flood_probability_0_1",)

    with pytest.raises(ValueError, match="epochs must be positive"):
        train_segmentation_candidate(
            training_contract,
            images,
            labels,
            evidence["workspace"] / "invalid-epoch-output",
            prepared_manifest_path=manifest,
            sidecar_path=evidence["sidecar"],
            trainer=trainer,
            epochs=True,
        )


@pytest.mark.parametrize("mutation", ["renamed", "unlisted", "mutated"])
def test_training_manifest_rejects_directory_or_byte_mutation(
    tmp_path: Path,
    mutation: str,
) -> None:
    evidence = build_synthetic_workspace(tmp_path)
    images = evidence["workspace"] / "tiles" / "images"
    labels = evidence["workspace"] / "tiles" / "labels"
    image = images / "image.tif"
    label = labels / "label.tif"
    _write_tile_pair(evidence, image, label, column_offset=0)
    manifest = evidence["workspace"] / "tiles" / "prepared-manifest.json"
    receipt = write_prepared_tile_manifest(
        evidence["contract"],
        images,
        labels,
        (
            TileMembership(
                image_path="image.tif",
                label_path="label.tif",
            ),
        ),
        manifest,
    )
    contract = replace(
        evidence["contract"],
        run_status="running",
        prepared_tile_manifest_sha256=receipt,
    )
    if mutation == "renamed":
        image.rename(images / "renamed.tif")
    elif mutation == "unlisted":
        (images / "extra.tif").write_bytes(b"unlisted")
    else:
        with rasterio.open(label, "r+") as raster:
            values = raster.read(1)
            values[0, 0] = 1 if values[0, 0] == 0 else 0
            raster.write(values, 1)
    with pytest.raises(ValueError, match="missing|exactly cover|checksum"):
        train_segmentation_candidate(
            contract,
            images,
            labels,
            evidence["workspace"] / "rejected-training-output",
            prepared_manifest_path=manifest,
            sidecar_path=evidence["sidecar"],
            trainer=lambda **_: None,
        )


def test_training_manifest_rejects_duplicate_paths_and_holdout_group(
    tmp_path: Path,
) -> None:
    evidence = build_synthetic_workspace(tmp_path)
    images = evidence["workspace"] / "tiles" / "images"
    labels = evidence["workspace"] / "tiles" / "labels"
    _write_tile_pair(
        evidence,
        images / "image.tif",
        labels / "label.tif",
        column_offset=0,
    )
    membership = TileMembership(
        image_path="image.tif",
        label_path="label.tif",
    )
    with pytest.raises(ValueError, match="duplicate"):
        write_prepared_tile_manifest(
            evidence["contract"],
            images,
            labels,
            (membership, membership),
            evidence["workspace"] / "duplicate-manifest.json",
        )
    _write_tile_pair(
        evidence,
        images / "holdout.tif",
        labels / "holdout.tif",
        column_offset=4,
    )
    with pytest.raises(ValueError, match="holdout group"):
        write_prepared_tile_manifest(
            evidence["contract"],
            images,
            labels,
            (
                TileMembership(
                    image_path="holdout.tif",
                    label_path="holdout.tif",
                ),
            ),
            evidence["workspace"] / "holdout-manifest.json",
        )
    _write_tile_pair(
        evidence,
        images / "boundary.tif",
        labels / "boundary.tif",
        column_offset=3,
    )
    with pytest.raises(ValueError, match="cross or fall outside"):
        write_prepared_tile_manifest(
            evidence["contract"],
            images,
            labels,
            (
                TileMembership(
                    image_path="boundary.tif",
                    label_path="boundary.tif",
                ),
            ),
            evidence["workspace"] / "boundary-manifest.json",
        )


@pytest.mark.parametrize("invalidity", ["nodata_metadata", "class_value"])
def test_training_manifest_rejects_invalid_exported_label_semantics(
    tmp_path: Path,
    invalidity: str,
) -> None:
    evidence = build_synthetic_workspace(tmp_path)
    images = evidence["workspace"] / "invalid-label-tiles" / "images"
    labels = evidence["workspace"] / "invalid-label-tiles" / "labels"
    image = images / "image.tif"
    label = labels / "label.tif"
    _write_tile_pair(evidence, image, label, column_offset=0)
    with rasterio.open(label, "r+") as raster:
        if invalidity == "nodata_metadata":
            raster.nodata = None
        else:
            values = raster.read(1)
            values[0, 0] = 2
            raster.write(values, 1)
    message = "nodata=255" if invalidity == "nodata_metadata" else r"\{0,1,255\}"
    with pytest.raises(ValueError, match=message):
        write_prepared_tile_manifest(
            evidence["contract"],
            images,
            labels,
            (TileMembership(image_path="image.tif", label_path="label.tif"),),
            evidence["workspace"] / "invalid-label-manifest.json",
        )


def test_training_rehashes_transform_sidecar_before_trainer(tmp_path: Path) -> None:
    evidence = build_synthetic_workspace(tmp_path)
    images = evidence["workspace"] / "tiles" / "images"
    labels = evidence["workspace"] / "tiles" / "labels"
    _write_tile_pair(
        evidence,
        images / "image.tif",
        labels / "label.tif",
        column_offset=0,
    )
    manifest = evidence["workspace"] / "tiles" / "prepared-manifest.json"
    receipt = write_prepared_tile_manifest(
        evidence["contract"],
        images,
        labels,
        (
            TileMembership(
                image_path="image.tif",
                label_path="label.tif",
            ),
        ),
        manifest,
    )
    contract = replace(
        evidence["contract"],
        run_status="running",
        prepared_tile_manifest_sha256=receipt,
    )
    evidence["sidecar"].write_text("{}\n", encoding="utf-8")
    called = False

    def trainer(**_: Any) -> None:
        nonlocal called
        called = True

    with pytest.raises(ValueError, match="sidecar checksum"):
        train_segmentation_candidate(
            contract,
            images,
            labels,
            evidence["workspace"] / "sidecar-rejected-training",
            prepared_manifest_path=manifest,
            sidecar_path=evidence["sidecar"],
            trainer=trainer,
        )
    assert called is False


def test_explicit_class1_softmax_preserves_nodata() -> None:
    logits = np.array(
        [
            [[0.0, 2.0], [OUTPUT_NODATA, -2.0]],
            [[0.0, -2.0], [OUTPUT_NODATA, 2.0]],
        ],
        dtype=np.float32,
    )
    probability = class1_probability_from_logits(logits)
    assert probability.shape == (1, 2, 2)
    assert probability[0, 0, 0] == pytest.approx(0.5)
    assert probability[0, 0, 1] < 0.02
    assert probability[0, 1, 0] == OUTPUT_NODATA
    assert probability[0, 1, 1] > 0.98


def test_mocked_geotiff_prediction_and_root_report_only_bridge(tmp_path: Path) -> None:
    evidence = build_synthetic_workspace(tmp_path)
    calls: dict[str, Any] = {}
    model = object()

    def model_loader(**kwargs: Any) -> VerifiedLoadedModel:
        return VerifiedLoadedModel(
            model=model,
            checkpoint_sha256=kwargs["checkpoint_sha256"],
            model_revision=kwargs["model_revision"],
            architecture=kwargs["architecture"],
            encoder=kwargs["encoder"],
            channel_count=kwargs["channel_count"],
            **_lineage_receipts(kwargs),
        )

    def predictor(**kwargs: Any) -> str:
        calls.update(kwargs)
        with rasterio.open(kwargs["input_raster"]) as source:
            encoded_float = source.read().astype(np.float32)
            normalized = kwargs["preprocess_fn"](encoded_float)
            profile = source.profile.copy()
        assert normalized.min() >= 0
        assert normalized.max() <= 1
        flood_logit = (normalized[4] + normalized[5]) * 2.0 - 1.0
        logits = np.stack([-flood_logit, flood_logit]).astype(np.float32)
        probability = kwargs["postprocess_fn"](logits)
        profile.update(count=1, dtype="float32", nodata=kwargs["output_nodata"])
        with rasterio.open(kwargs["output_raster"], "w", **profile) as target:
            target.write(probability)
        return kwargs["output_raster"]

    grid = run_prediction(
        evidence["inference_contract"],
        encoded_feature_path=evidence["encoded"],
        sidecar_path=evidence["sidecar"],
        checkpoint_path=evidence["checkpoint"],
        output_path=evidence["probability"],
        prepared_manifest_path=evidence["lineage_manifest"],
        model_loader=model_loader,
        predictor=predictor,
    )
    assert grid.count == 1
    assert grid.descriptions == ("flood_probability_0_1",)
    assert calls["num_classes"] == 2
    assert calls["input_bands"] == list(range(1, 9))
    assert calls["blend_mode"] == "spline"
    assert calls["output_nodata"] == OUTPUT_NODATA
    assert calls["model"] is model
    assert "geoai" not in sys.modules

    with rasterio.open(evidence["probability"]) as source:
        values = source.read(1).reshape(-1)
        tags = source.tags()
    assert tags["source_timestamp"] == evidence["contract"].source_timestamp
    assert tags["confidence_class"] == "low"
    assert json.loads(tags["assumptions"]) == list(evidence["contract"].assumptions)
    assert tags["official_warning"] == "false"
    assert tags["operational_status"] == "non_operational"
    assert tags["can_feed_decision_layer"] == "false"
    assert tags["model_sha256"] == evidence["contract"].model_sha256
    assert len(tags["generated_at"]) > 20
    summary = aggregate_probability_cells(
        values,
        subdistrict_id="SYNTHETIC-AREA-001",
        subdistrict_name="Synthetic contract area",
        nodata=OUTPUT_NODATA,
        probability_threshold=evidence["contract"].probability_threshold,
        source_metadata={
            "dataset_mode": "candidate",
            "operational_status": evidence["inference_contract"].operational_status,
            "run_status": evidence["inference_contract"].run_status,
            "source_name": evidence["contract"].source_name,
            "source_timestamp": evidence["contract"].source_timestamp,
            "confidence_class": evidence["contract"].confidence_class,
            "assumptions": list(evidence["contract"].assumptions),
            "processing_scope": evidence["contract"].processing_scope,
            "processing_allowed": evidence["contract"].processing_allowed,
            "reference_mask_status": evidence["contract"].reference_mask_status,
            "validation_metrics": {
                "iou": 0.4,
                "f1_dice": 0.57,
                "precision": 0.5,
                "recall": 0.67,
                "area_error_ratio": 0.2,
                "brier_score": 0.18,
                "expected_calibration_error": 0.08,
            },
            "can_feed_decision_layer": False,
            "reason_blocked": evidence["contract"].reason_blocked,
        },
        allow_report_only=True,
    )
    assert summary["sample_pixel_count"] == 64
    assert 0 <= summary["mean_flood_probability_0_1"] <= 1
    assert summary["aggregation_status"] == "report_only"
    assert summary["eligible_for_decision_layer"] is False
    assert summary["eligible_for_fpps"] is False

    proof = write_proposal_proof_artifacts(
        evidence["inference_contract"],
        evidence["probability"],
        TileExportReceipt(
            grid=grid,
            prepared_manifest_relative_path="prepared-tile-manifest.json",
            prepared_manifest_sha256=evidence[
                "inference_contract"
            ].prepared_tile_manifest_sha256,
            training_tile_count=1,
            holdout_tile_count=1,
            rejected_boundary_tile_count=0,
        ),
        summary,
        evidence["workspace"] / "proposal-proof",
        execution_mode="mocked_unit",
        training_execution="mocked_wrapper_only",
    )
    receipt = validate_proposal_proof_receipt(proof.receipt_path)
    assert receipt["execution_mode"] == "mocked_unit"
    assert receipt["actual_geoai_calls"] == []
    assert receipt["aggregation"]["status"] == "report_only"
    assert b"\r\n" not in proof.receipt_path.read_bytes()
    assert proof.thumbnail_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert len(proof.receipt_file_sha256) == 64


def test_prediction_rejects_checkpoint_mismatch_before_predictor(tmp_path: Path) -> None:
    evidence = build_synthetic_workspace(tmp_path)
    evidence["checkpoint"].write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum"):
        run_prediction(
            evidence["inference_contract"],
            encoded_feature_path=evidence["encoded"],
            sidecar_path=evidence["sidecar"],
            checkpoint_path=evidence["checkpoint"],
            output_path=evidence["probability"],
            prepared_manifest_path=evidence["lineage_manifest"],
            model_loader=lambda **_: pytest.fail("model loader must not be called"),
            predictor=lambda **_: None,
        )


def test_prediction_rehashes_previously_validated_feature_before_predictor(
    tmp_path: Path,
) -> None:
    evidence = build_synthetic_workspace(tmp_path)
    validate_prepared_inputs(
        evidence["contract"],
        evidence["encoded"],
        evidence["mask"],
        evidence["sidecar"],
    )
    with rasterio.open(evidence["encoded"], "r+") as raster:
        values = raster.read(1)
        values[0, 0] = (int(values[0, 0]) + 1) % 256
        raster.write(values, 1)
    called = False

    def predictor(**_: Any) -> None:
        nonlocal called
        called = True

    with pytest.raises(ValueError, match="Encoded feature checksum"):
        run_prediction(
            evidence["inference_contract"],
            encoded_feature_path=evidence["encoded"],
            sidecar_path=evidence["sidecar"],
            checkpoint_path=evidence["checkpoint"],
            output_path=evidence["probability"],
            prepared_manifest_path=evidence["lineage_manifest"],
            model_loader=lambda **_: pytest.fail("model loader must not be called"),
            predictor=predictor,
        )
    assert called is False


def test_prediction_rejects_model_not_bound_to_verified_checkpoint(
    tmp_path: Path,
) -> None:
    evidence = build_synthetic_workspace(tmp_path)
    called = False

    def unrelated_loader(**kwargs: Any) -> VerifiedLoadedModel:
        return VerifiedLoadedModel(
            model=object(),
            checkpoint_sha256="0" * 64,
            model_revision=kwargs["model_revision"],
            architecture=kwargs["architecture"],
            encoder=kwargs["encoder"],
            channel_count=kwargs["channel_count"],
            **_lineage_receipts(kwargs),
        )

    def predictor(**_: Any) -> None:
        nonlocal called
        called = True

    with pytest.raises(ValueError, match="Loaded model receipt"):
        run_prediction(
            evidence["inference_contract"],
            encoded_feature_path=evidence["encoded"],
            sidecar_path=evidence["sidecar"],
            checkpoint_path=evidence["checkpoint"],
            output_path=evidence["probability"],
            prepared_manifest_path=evidence["lineage_manifest"],
            model_loader=unrelated_loader,
            predictor=predictor,
        )
    assert called is False


@pytest.mark.parametrize("substitution", ["prepared_manifest", "input_manifest"])
def test_prediction_rejects_checkpoint_training_lineage_substitution(
    tmp_path: Path,
    substitution: str,
) -> None:
    evidence = build_synthetic_workspace(tmp_path)
    original = evidence["inference_contract"]
    original_lineage = original.training_lineage_receipts()
    prepared_manifest = evidence["lineage_manifest"]
    if substitution == "prepared_manifest":
        prepared_manifest = evidence["workspace"] / "substitute-manifest.json"
        prepared_manifest.write_text('{"substitute":true}\n', encoding="utf-8")
        contract = replace(
            original,
            prepared_tile_manifest_sha256=sha256(prepared_manifest),
        )
    else:
        contract = replace(
            original,
            input_manifest_rows=(
                replace(original.input_manifest_rows[0], sha256="0" * 64),
                *original.input_manifest_rows[1:],
            ),
        )
    contract.validate()

    def original_checkpoint_loader(**kwargs: Any) -> VerifiedLoadedModel:
        return VerifiedLoadedModel(
            model=object(),
            checkpoint_sha256=kwargs["checkpoint_sha256"],
            model_revision=kwargs["model_revision"],
            architecture=kwargs["architecture"],
            encoder=kwargs["encoder"],
            channel_count=kwargs["channel_count"],
            **original_lineage,
        )

    with pytest.raises(ValueError, match="Loaded model receipt"):
        run_prediction(
            contract,
            encoded_feature_path=evidence["encoded"],
            sidecar_path=evidence["sidecar"],
            checkpoint_path=evidence["checkpoint"],
            output_path=evidence["probability"],
            prepared_manifest_path=prepared_manifest,
            model_loader=original_checkpoint_loader,
            predictor=lambda **_: pytest.fail("predictor must not be called"),
        )


def test_prediction_rehashes_transform_sidecar_before_model_load(
    tmp_path: Path,
) -> None:
    evidence = build_synthetic_workspace(tmp_path)
    evidence["sidecar"].write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="sidecar checksum"):
        run_prediction(
            evidence["inference_contract"],
            encoded_feature_path=evidence["encoded"],
            sidecar_path=evidence["sidecar"],
            checkpoint_path=evidence["checkpoint"],
            output_path=evidence["probability"],
            prepared_manifest_path=evidence["lineage_manifest"],
            model_loader=lambda **_: pytest.fail("model loader must not be called"),
            predictor=lambda **_: None,
        )


def test_prediction_rehashes_prepared_manifest_before_model_load(
    tmp_path: Path,
) -> None:
    evidence = build_synthetic_workspace(tmp_path)
    evidence["lineage_manifest"].write_text(
        '{"tampered":true}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Prepared tile manifest checksum"):
        run_prediction(
            evidence["inference_contract"],
            encoded_feature_path=evidence["encoded"],
            sidecar_path=evidence["sidecar"],
            checkpoint_path=evidence["checkpoint"],
            output_path=evidence["probability"],
            prepared_manifest_path=evidence["lineage_manifest"],
            model_loader=lambda **_: pytest.fail("model loader must not be called"),
            predictor=lambda **_: None,
        )


@pytest.mark.parametrize(
    "collision",
    ["encoded", "checkpoint", "sidecar", "lineage_manifest"],
)
def test_prediction_rejects_protected_output_collisions(
    tmp_path: Path,
    collision: str,
) -> None:
    evidence = build_synthetic_workspace(tmp_path)
    with pytest.raises(ValueError, match="cannot overwrite"):
        run_prediction(
            evidence["inference_contract"],
            encoded_feature_path=evidence["encoded"],
            sidecar_path=evidence["sidecar"],
            checkpoint_path=evidence["checkpoint"],
            output_path=evidence[collision],
            prepared_manifest_path=evidence["lineage_manifest"],
            model_loader=lambda **_: pytest.fail("model loader must not be called"),
            predictor=lambda **_: None,
        )


def test_prediction_requires_explicit_replace_policy_for_existing_output(
    tmp_path: Path,
) -> None:
    evidence = build_synthetic_workspace(tmp_path)
    evidence["probability"].write_bytes(b"existing output")
    with pytest.raises(FileExistsError, match="replace_output=True"):
        run_prediction(
            evidence["inference_contract"],
            encoded_feature_path=evidence["encoded"],
            sidecar_path=evidence["sidecar"],
            checkpoint_path=evidence["checkpoint"],
            output_path=evidence["probability"],
            prepared_manifest_path=evidence["lineage_manifest"],
            model_loader=lambda **_: pytest.fail("model loader must not be called"),
            predictor=lambda **_: None,
        )


def test_prediction_never_publishes_an_unvalidated_partial_raster(
    tmp_path: Path,
) -> None:
    evidence = build_synthetic_workspace(tmp_path)

    def model_loader(**kwargs: Any) -> VerifiedLoadedModel:
        return VerifiedLoadedModel(
            model=object(),
            checkpoint_sha256=kwargs["checkpoint_sha256"],
            model_revision=kwargs["model_revision"],
            architecture=kwargs["architecture"],
            encoder=kwargs["encoder"],
            channel_count=kwargs["channel_count"],
            **_lineage_receipts(kwargs),
        )

    def invalid_predictor(**kwargs: Any) -> None:
        with rasterio.open(kwargs["input_raster"]) as source:
            profile = source.profile.copy()
            values = np.full((1, source.height, source.width), 1.5, dtype=np.float32)
        profile.update(count=1, dtype="float32", nodata=kwargs["output_nodata"])
        with rasterio.open(kwargs["output_raster"], "w", **profile) as output:
            output.write(values)

    with pytest.raises(RasterValidationError, match=r"must be in \[0,1\]"):
        run_prediction(
            evidence["inference_contract"],
            encoded_feature_path=evidence["encoded"],
            sidecar_path=evidence["sidecar"],
            checkpoint_path=evidence["checkpoint"],
            output_path=evidence["probability"],
            prepared_manifest_path=evidence["lineage_manifest"],
            model_loader=model_loader,
            predictor=invalid_predictor,
        )
    assert not evidence["probability"].exists()
    assert not list(evidence["workspace"].glob("*.partial.tif"))


def _write_tile_pair(
    evidence: dict[str, Any],
    image_path: Path,
    label_path: Path,
    *,
    column_offset: int,
    row_offset: int = 0,
    preserve_label_nodata: bool = True,
) -> None:
    window = Window(column_offset, row_offset, 4, 4)
    image_path.parent.mkdir(parents=True, exist_ok=True)
    label_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(evidence["encoded"]) as source:
        image_profile = source.profile.copy()
        image_profile.update(
            width=4,
            height=4,
            transform=source.window_transform(window),
        )
        image_values = source.read(window=window)
        descriptions = source.descriptions
    with rasterio.open(image_path, "w", **image_profile) as target:
        target.write(image_values)
        for index, description in enumerate(descriptions, start=1):
            target.set_band_description(index, description)
    with rasterio.open(evidence["mask"]) as source:
        label_profile = source.profile.copy()
        label_profile.update(
            width=4,
            height=4,
            transform=source.window_transform(window),
        )
        label_values = source.read(window=window)
        description = source.descriptions[0]
    if not preserve_label_nodata:
        label_profile.pop("nodata", None)
    with rasterio.open(label_path, "w", **label_profile) as target:
        target.write(label_values)
        target.set_band_description(1, description)


def _lineage_receipts(values: dict[str, Any]) -> dict[str, str]:
    return {
        name: values[name]
        for name in (
            "prepared_tile_manifest_sha256",
            "preprocessing_sidecar_sha256",
            "encoded_feature_stack_sha256",
            "reference_mask_sha256",
            "input_manifest_sha256",
        )
    }
