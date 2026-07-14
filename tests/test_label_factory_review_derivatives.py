from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

from floodguard.label_factory.review_derivatives import (
    REVIEW_DERIVATIVE_BUILD_SPEC_SCHEMA,
    REVIEW_DERIVATIVE_LINEAGE_RECEIPT_SCHEMA,
    ReviewDerivativeLineageError,
    build_review_derivative_lineage_receipt,
    load_review_derivative_lineage_receipt,
    validate_derivative_context_against_receipt,
    write_review_derivative_lineage_receipt,
)
from floodguard.label_factory.review_bundle import (
    ReviewBundleError,
    ReviewPurpose,
    write_blinded_review_bundle,
)
from floodguard.label_factory.review_workflow import (
    ReviewWorkflowError,
    parse_completed_review_csv,
)
from test_label_factory_review_bundle import (
    _context_layers,
    _processing_receipt,
    _queries,
    _queries_bound_to,
)
from test_label_factory_review_workflow import (
    _completed_review_frame,
    _geometry_parts,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _spec(
    root: Path,
    processing_receipt: dict[str, object],
) -> dict[str, object]:
    assets = processing_receipt["assets"]
    assert isinstance(assets, list)
    by_role = {str(row["event_relative_role"]): row for row in assets}
    pre = by_role["pre_event"]
    event = by_role["event_time"]
    source_inputs = []
    for row in assets:
        source_path = root / str(row["asset_id"]) / "synthetic_processed.tif"
        source_inputs.append(
            {
                "asset_id": row["asset_id"],
                "processed_file_path": str(source_path),
                "processed_file_sha256": _sha(source_path),
                "polarizations": ["VV", "VH"],
                "band_by_polarization": {"VV": "VV_db", "VH": "VH_db"},
            }
        )
    outputs = root / "outputs"
    outputs.mkdir(parents=True)
    output_paths = {
        "vv_change": outputs / "vv_change.tif",
        "vh_change": outputs / "vh_change.tif",
        "fixed_stretch_change_composite": outputs / "change_composite.tif",
    }
    for role, path in output_paths.items():
        path.write_bytes(f"synthetic reviewer derivative:{role}".encode("utf-8"))

    common = {
        "output_crs": pre["output_crs"],
        "affine_transform": pre["affine_transform"],
        "width_pixels": pre["width_pixels"],
        "height_pixels": pre["height_pixels"],
        "nodata_convention": "nodata=-9999; valid only where all declared inputs are valid",
        "confidence_class": "low",
        "assumptions": (
            "Synthetic byte fixture; display evidence only, never flood truth."
        ),
        "formal_review_display_only": True,
        "allowed_for_blinded_review": True,
        "query_model_only": True,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }
    layers: list[dict[str, object]] = []
    for role, polarization in (("vv_change", "VV"), ("vh_change", "VH")):
        path = output_paths[role]
        layers.append(
            {
                "derivative_id": f"SYNTHETIC-{polarization}-CHANGE-V1",
                "layer_role": role,
                "output_file_path": str(path),
                "output_file_sha256": _sha(path),
                "display_name": f"Synthetic {polarization} pre minus event dB",
                "path_hint": f"review_context/{path.name}",
                "output_dtype": "float32",
                "transformation_parameters": {
                    "operation": "pre_minus_event_db",
                    "expression": "pre_db - event_db",
                    "polarization": polarization,
                    "pre_input_asset_id": pre["asset_id"],
                    "event_input_asset_id": event["asset_id"],
                    "pre_band": f"{polarization}_db",
                    "event_band": f"{polarization}_db",
                    "input_units": "dB",
                    "output_units": "dB_change",
                    "validity_rule": "valid_where_both_inputs_valid",
                },
                "display_parameters": {
                    "renderer": "single_band_fixed_stretch",
                    "stretch_min": -10.0,
                    "stretch_max": 10.0,
                    "gamma": 1.0,
                    "clamp": True,
                    "color_map_id": "floodguard_diverging_v1",
                    "color_stops": [
                        {"value": -10.0, "hex": "#2166AC"},
                        {"value": 0.0, "hex": "#F7F7F7"},
                        {"value": 10.0, "hex": "#B2182B"},
                    ],
                    "resampling": "nearest",
                },
                **common,
            }
        )
    composite = output_paths["fixed_stretch_change_composite"]
    layers.append(
        {
            "derivative_id": "SYNTHETIC-CHANGE-RGB-V1",
            "layer_role": "fixed_stretch_change_composite",
            "output_file_path": str(composite),
            "output_file_sha256": _sha(composite),
            "display_name": "Synthetic fixed-stretch VV/VH change RGB",
            "path_hint": f"review_context/{composite.name}",
            "output_dtype": "uint8",
            "transformation_parameters": {
                "operation": "fixed_stretch_rgb_composite",
                "input_derivative_ids": [
                    "SYNTHETIC-VV-CHANGE-V1",
                    "SYNTHETIC-VH-CHANGE-V1",
                ],
                "red_expression": "clamp((vv_change_db + 10.0) * 12.75, 0, 255)",
                "green_expression": "clamp((vh_change_db + 10.0) * 12.75, 0, 255)",
                "blue_expression": "clamp(((vv_change_db-vh_change_db)+10.0)*12.75,0,255)",
                "validity_rule": "valid_where_all_inputs_valid",
                "channel_min": 0,
                "channel_max": 255,
            },
            "display_parameters": {
                "renderer": "rgb_pre_stretched",
                "red_band": 1,
                "green_band": 2,
                "blue_band": 3,
                "gamma": 1.0,
                "resampling": "nearest",
            },
            **common,
        }
    )
    return {
        "artifact_schema": REVIEW_DERIVATIVE_BUILD_SPEC_SCHEMA,
        "derivative_set_id": "SYNTHETIC-REVIEW-DERIVATIVES-V1",
        "event_id": "TH-MAESAI-2024-09",
        "generated_at_utc": "2024-09-21T01:00:00Z",
        "processing_software": "synthetic_derivative_fixture",
        "processing_software_version": "1.0.0-test",
        "source_inputs": source_inputs,
        "layers": layers,
        "assumptions": (
            "Synthetic derivative fixture only; no flood observation or warning."
        ),
        "formal_review_display_only": True,
        "allowed_for_blinded_review": True,
        "query_model_only": True,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }


def _receipt(tmp_path: Path) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    processing_root = tmp_path / "processing"
    processing = _processing_receipt(processing_root)
    spec = _spec(processing_root, processing)
    receipt = build_review_derivative_lineage_receipt(
        spec,
        processing_alignment_receipt=processing,
        validated_at_utc="2024-09-21T02:00:00Z",
        allow_ungoverned_fixture=True,
    )
    return processing, spec, receipt


def test_derivative_receipt_rehashes_sources_outputs_and_is_immutable(
    tmp_path: Path,
) -> None:
    _processing, _spec_payload, receipt = _receipt(tmp_path)

    assert receipt["artifact_schema"] == REVIEW_DERIVATIVE_LINEAGE_RECEIPT_SCHEMA
    assert receipt["layer_count"] == 3
    assert {row["layer_role"] for row in receipt["layers"]} == {
        "vv_change",
        "vh_change",
        "fixed_stretch_change_composite",
    }
    assert len(receipt["source_raster_binding_sha256"]) == 64
    assert receipt["production_review_eligible"] is False
    assert receipt["eligible_for_fpps"] is False

    output = write_review_derivative_lineage_receipt(
        receipt, tmp_path / "review_derivatives_v1.json"
    )
    assert load_review_derivative_lineage_receipt(output) == receipt
    with pytest.raises(ReviewDerivativeLineageError, match="immutable"):
        write_review_derivative_lineage_receipt(receipt, output)


def test_derivative_receipt_fails_on_source_output_and_self_hash_tampering(
    tmp_path: Path,
) -> None:
    processing_root = tmp_path / "processing"
    processing = _processing_receipt(processing_root)
    spec = _spec(processing_root, processing)
    first_source = Path(spec["source_inputs"][0]["processed_file_path"])
    first_source.write_bytes(b"tampered source after declared hash")
    with pytest.raises(ReviewDerivativeLineageError, match="bytes do not match"):
        build_review_derivative_lineage_receipt(
            spec,
            processing_alignment_receipt=processing,
            allow_ungoverned_fixture=True,
        )

    _processing, _spec_payload, receipt = _receipt(tmp_path / "fresh")
    changed = deepcopy(receipt)
    changed["layers"][0]["display_name"] = "tampered"
    with pytest.raises(ReviewDerivativeLineageError, match="self-hash|build-spec"):
        load_review_derivative_lineage_receipt(changed)


def test_derivative_receipt_rejects_dynamic_stretch_and_unsafe_flags(
    tmp_path: Path,
) -> None:
    processing_root = tmp_path / "processing"
    processing = _processing_receipt(processing_root)
    spec = _spec(processing_root, processing)
    spec["layers"][0]["display_parameters"]["color_map_id"] = "auto_percentile"
    with pytest.raises(ReviewDerivativeLineageError, match="dynamic display"):
        build_review_derivative_lineage_receipt(
            spec,
            processing_alignment_receipt=processing,
            allow_ungoverned_fixture=True,
        )

    other_root = tmp_path / "other"
    other_processing = _processing_receipt(other_root)
    safe_spec = _spec(other_root, other_processing)
    safe_spec["layers"][0]["eligible_for_fpps"] = True
    with pytest.raises(ReviewDerivativeLineageError, match="unsafe"):
        build_review_derivative_lineage_receipt(
            safe_spec,
            processing_alignment_receipt=other_processing,
            allow_ungoverned_fixture=True,
        )


def test_semantically_invalid_but_rehashed_transformation_is_rejected(
    tmp_path: Path,
) -> None:
    _processing, _spec_payload, receipt = _receipt(tmp_path)
    changed = deepcopy(receipt)
    vv_layer = next(
        layer for layer in changed["layers"] if layer["layer_role"] == "vv_change"
    )
    vv_layer["transformation_parameters"]["operation"] = "event_minus_pre_db"
    vv_layer["transformation_parameters_sha256"] = _json_sha(
        vv_layer["transformation_parameters"]
    )
    normalized_spec = {
        "artifact_schema": REVIEW_DERIVATIVE_BUILD_SPEC_SCHEMA,
        "derivative_set_id": changed["derivative_set_id"],
        "event_id": changed["event_id"],
        "generated_at_utc": changed["generated_at_utc"],
        "processing_software": changed["processing_software"],
        "processing_software_version": changed["processing_software_version"],
        "source_rasters": changed["source_rasters"],
        "layers": changed["layers"],
        "assumptions": changed["assumptions"],
        "formal_review_display_only": True,
        "allowed_for_blinded_review": True,
        "query_model_only": True,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }
    changed["build_spec_sha256"] = _json_sha(normalized_spec)
    changed["receipt_sha256"] = _json_sha(
        {key: value for key, value in changed.items() if key != "receipt_sha256"}
    )

    with pytest.raises(ReviewDerivativeLineageError, match="canonical pre-minus-event"):
        load_review_derivative_lineage_receipt(changed)


def test_receipt_preserves_real_fractional_second_acquisitions(
    tmp_path: Path,
) -> None:
    processing_root = tmp_path / "processing"
    processing = _processing_receipt(processing_root)
    for asset in processing["assets"]:
        asset["acquisition_time_utc"] = asset["acquisition_time_utc"].replace(
            "Z", ".123456Z"
        )
    processing["receipt_sha256"] = _json_sha(
        {
            key: value
            for key, value in processing.items()
            if key != "receipt_sha256"
        }
    )
    spec = _spec(processing_root, processing)

    receipt = build_review_derivative_lineage_receipt(
        spec,
        processing_alignment_receipt=processing,
        validated_at_utc="2024-09-21T02:00:00Z",
        allow_ungoverned_fixture=True,
    )

    assert all(
        source["acquisition_time_utc"].endswith(".123456Z")
        for source in receipt["source_rasters"]
    )

def test_derivative_context_must_exactly_match_receipt(tmp_path: Path) -> None:
    processing, _spec_payload, receipt = _receipt(tmp_path)
    review = pd.DataFrame(
        [
            {
                "event_id": receipt["event_id"],
                "grid_contract_sha256": receipt["grid_contract_sha256"],
                "source_registry_sha256": receipt["source_registry_sha256"],
                "processing_alignment_receipt_sha256": processing["receipt_sha256"],
            }
        ]
    )
    context = pd.DataFrame(
        [
            {
                "context_layer_id": layer["derivative_id"],
                "event_id": receipt["event_id"],
                "layer_role": layer["layer_role"],
                "source_registry_sha256": receipt["source_registry_sha256"],
                "source_asset_id": layer["derivative_id"],
                "source_product_id": receipt["derivative_set_id"],
                "display_name": layer["display_name"],
                "path_hint": layer["path_hint"],
                "crs": layer["output_crs"],
                "acquisition_time_utc": layer["acquisition_time_utc"],
                "source_sha256": receipt["source_raster_binding_sha256"],
                "processed_layer_sha256": layer["output_file_sha256"],
                "allowed_for_blinded_review": True,
                "confidence_class": layer["confidence_class"],
                "assumptions": layer["assumptions"],
            }
            for layer in receipt["layers"]
        ]
    )

    validate_derivative_context_against_receipt(
        receipt,
        review_manifest=review,
        context_manifest=context,
    )
    context.loc[0, "processed_layer_sha256"] = "f" * 64
    with pytest.raises(ReviewDerivativeLineageError, match="does not match"):
        validate_derivative_context_against_receipt(
            receipt,
            review_manifest=review,
            context_manifest=context,
        )


def _derivative_context_rows(receipt: dict[str, object]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "context_layer_id": layer["derivative_id"],
                "event_id": receipt["event_id"],
                "layer_role": layer["layer_role"],
                "source_registry_sha256": receipt["source_registry_sha256"],
                "source_asset_id": layer["derivative_id"],
                "source_product_id": receipt["derivative_set_id"],
                "display_name": layer["display_name"],
                "path_hint": layer["path_hint"],
                "crs": layer["output_crs"],
                "acquisition_time_utc": layer["acquisition_time_utc"],
                "source_sha256": receipt["source_raster_binding_sha256"],
                "processed_layer_sha256": layer["output_file_sha256"],
                "allowed_for_blinded_review": True,
                "confidence_class": layer["confidence_class"],
                "assumptions": layer["assumptions"],
            }
            for layer in receipt["layers"]
        ]
    )


def test_blinded_bundle_admits_only_receipt_bound_change_displays(
    tmp_path: Path,
) -> None:
    processing, _spec_payload, derivative = _receipt(tmp_path / "evidence")
    queries = _queries_bound_to(_queries(), processing)
    queries["source_registry_sha256"] = processing["source_registry_sha256"]
    context = _context_layers(processing)
    context["source_registry_sha256"] = processing["source_registry_sha256"]
    context = pd.concat(
        [context, _derivative_context_rows(derivative)], ignore_index=True
    )

    written = write_blinded_review_bundle(
        queries,
        tmp_path / "derivative-bundle",
        review_purpose=ReviewPurpose.ACQUISITION_PRIMARY,
        processing_alignment_receipt=processing,
        derivative_lineage_receipt=derivative,
        allow_ungoverned_fixture=True,
        context_layers=context,
    )

    assert "review_derivative_lineage_receipt" in written
    manifest = pd.read_csv(written["bundle_manifest"], keep_default_na=False)
    assert "review_derivative_lineage_provenance" in set(manifest["bundle_role"])
    assert manifest["review_derivative_lineage_receipt_sha256"].eq(
        derivative["receipt_sha256"]
    ).all()
    assert manifest["governed_derivative_layers_included"].eq(True).all()
    assert manifest["eligible_for_fpps"].eq(False).all()

    completed = _completed_review_frame()
    query = queries.iloc[0]
    completed.loc[0, "tile_id"] = query["tile_id"]
    completed.loc[0, "query_region_id"] = query["query_region_id"]
    completed.loc[0, "protocol_version"] = "label_factory_protocol_v1"
    completed.loc[0, "tool_version"] = "qgis_manual_review_v1"
    completed.loc[0, "source_timestamp"] = query["source_timestamp"]
    completed.loc[0, "review_started_at_utc"] = "2030-01-01T01:00:00Z"
    completed.loc[0, "review_finished_at_utc"] = "2030-01-01T01:10:00Z"
    completed.loc[0, "created_at_utc"] = "2030-01-01T01:11:00Z"
    completed.loc[0, "locked_at_utc"] = "2030-01-01T01:12:00Z"
    completed.loc[0, "evidence_layers_used"] = (
        "pre_event_vv;event_time_vv;vv_change;vh_change;"
        "fixed_stretch_change_composite;dem_hillshade"
    )
    completed.loc[0, "reviewed_extent"] = query["geometry_wkt"] if "geometry_wkt" in query else (
        "POLYGON ((590000 2264000, 590640 2264000, 590640 2264640, "
        "590000 2264640, 590000 2264000))"
    )
    completed.loc[0, "geometry_wkt"] = (
        "POLYGON ((590000 2264000, 590010 2264000, 590010 2264010, "
        "590000 2264000))"
    )
    parts = _geometry_parts()
    parts.loc[0, "geometry_wkt"] = completed.loc[0, "geometry_wkt"]
    records = parse_completed_review_csv(
        completed,
        expected_review_regions=written["review_regions"],
        geometry_parts=parts,
        bundle_manifest=written["bundle_manifest"],
        context_layers=written["context_layers"],
        allow_ungoverned_fixture=True,
    )
    assert records[0].query_region_id == query["query_region_id"]

    too_early = completed.copy()
    too_early.loc[0, "review_started_at_utc"] = "2024-09-16T01:00:00Z"
    too_early.loc[0, "review_finished_at_utc"] = "2024-09-16T01:10:00Z"
    too_early.loc[0, "created_at_utc"] = "2024-09-16T01:11:00Z"
    too_early.loc[0, "locked_at_utc"] = "2024-09-16T01:12:00Z"
    with pytest.raises(ReviewWorkflowError, match="governed review evidence existed"):
        parse_completed_review_csv(
            too_early,
            expected_review_regions=written["review_regions"],
            geometry_parts=parts,
            bundle_manifest=written["bundle_manifest"],
            context_layers=written["context_layers"],
            allow_ungoverned_fixture=True,
        )

    with pytest.raises(ReviewBundleError, match="derivative-lineage receipt"):
        write_blinded_review_bundle(
            queries,
            tmp_path / "missing-derivative-receipt",
            review_purpose=ReviewPurpose.ACQUISITION_PRIMARY,
            processing_alignment_receipt=processing,
            allow_ungoverned_fixture=True,
            context_layers=context,
        )

    changed = context.copy()
    changed.loc[
        changed["layer_role"].eq("vv_change"), "processed_layer_sha256"
    ] = "f" * 64
    with pytest.raises(ReviewBundleError, match="does not match"):
        write_blinded_review_bundle(
            queries,
            tmp_path / "mismatched-derivative-context",
            review_purpose=ReviewPurpose.ACQUISITION_PRIMARY,
            processing_alignment_receipt=processing,
            derivative_lineage_receipt=derivative,
            allow_ungoverned_fixture=True,
            context_layers=changed,
        )


def test_derivative_receipt_cli_requires_governance() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "build_review_derivative_lineage_receipt.py"),
            "--help",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "governance-package" in result.stdout
    assert "processing-alignment-receipt" in result.stdout
    assert "build-spec" in result.stdout
