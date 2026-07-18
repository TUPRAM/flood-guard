from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from floodguard.probability_consequences import (
    ProbabilityConsequenceError,
    create_signed_consequence_receipt,
    verify_signed_consequence_receipt,
)
from floodguard.probability_aggregation import ProbabilityAggregationError


ROOT = Path(__file__).resolve().parents[1]
NODATA = -9999.0
KEY = b"floodguard-consequence-test-key-32-bytes"
KEY_ID = "consequence-test-v1"
GENERATED_AT = "2026-07-18T10:00:00Z"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_metadata(*, official: bool) -> dict[str, object]:
    source = json.loads(
        (ROOT / "packages/contracts/examples/model-run.candidate.json").read_text(
            encoding="utf-8"
        )
    )
    source["source_name"] = "Synthetic consequence contract probability"
    if official:
        source.update(
            {
                "dataset_mode": "official_input",
                "operational_status": "planning_only",
                "confidence_class": "medium",
                "reference_mask_status": "confirmed_for_model_purpose",
                "can_feed_decision_layer": True,
                "reason_blocked": "",
                "external_output_workspace": "external-workspace/consequence-test",
            }
        )
        source["input_manifest_rows"].extend(
            [
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
            ]
        )
        source["validation_metrics"]["expected_calibration_error"] = 0.04
    return source


def _write_raster(path: Path) -> Path:
    values = np.full((32, 32), 0.2, dtype=np.float32)
    values[:, 16:] = 0.8
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=32,
        height=32,
        count=1,
        dtype="float32",
        crs="EPSG:32647",
        transform=from_origin(600000.0, 2200320.0, 10.0, 10.0),
        nodata=NODATA,
    ) as target:
        target.write(values, 1)
        target.set_band_description(1, "flood_probability_0_1")
    return path


def _write_geojson(path: Path, *, kind: str, bad_bridge: bool = False) -> Path:
    if kind == "road_segments":
        features = [
            {
                "type": "Feature",
                "properties": {
                    "road_id": "ROAD-LOW",
                    "subdistrict_id": "AREA-WEST",
                    "road_class": "secondary",
                    "bridge_flag": False,
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [600010.0, 2200160.0],
                        [600140.0, 2200160.0],
                    ],
                },
            },
            {
                "type": "Feature",
                "properties": {
                    "road_id": "ROAD-HIGH",
                    "subdistrict_id": "AREA-EAST",
                    "road_class": "primary",
                    "bridge_flag": "yes" if bad_bridge else True,
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [600180.0, 2200160.0],
                        [600310.0, 2200160.0],
                    ],
                },
            },
        ]
    else:
        features = [
            {
                "type": "Feature",
                "properties": {
                    "facility_id": "FACILITY-CANDIDATE",
                    "subdistrict_id": "AREA-WEST",
                    "facility_type": "community_facility",
                    "verification_status": "open_context_candidate",
                    "emergency_role": "no_confirmed_emergency_role",
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [600050.0, 2200160.0],
                },
            },
            {
                "type": "Feature",
                "properties": {
                    "facility_id": "FACILITY-VERIFIED",
                    "subdistrict_id": "AREA-EAST",
                    "facility_type": "evacuation_facility",
                    "verification_status": "agency_verified",
                    "emergency_role": "designated_evacuation",
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [600250.0, 2200160.0],
                },
            },
        ]
    document = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "EPSG:32647"}},
        "features": features,
    }
    path.write_text(
        json.dumps(document, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    return path


def _raster_receipt(source: dict[str, object], path: Path) -> dict[str, object]:
    return {
        "run_id": source["run_id"],
        "model_run_manifest_sha256": _canonical_sha(source),
        "probability_raster_sha256": _sha(path),
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


def _geometry_receipt(
    path: Path, *, kind: str, authoritative: bool
) -> dict[str, object]:
    return {
        "dataset_id": f"SYNTHETIC-{kind.upper()}",
        "study_area": "synthetic_contract_grid",
        "data_version": "contract-test-1",
        "sha256": _sha(path),
        "source_name": f"Synthetic {kind} contract geometry",
        "source_timestamp": "2024-09-01T00:00:00Z",
        "crs": "EPSG:32647",
        "feature_kind": kind,
        "feature_id_field": "road_id" if kind == "road_segments" else "facility_id",
        "area_id_field": "subdistrict_id",
        "feature_count": 2,
        "authority_status": (
            "authoritative_for_study_area"
            if authoritative
            else "provenance_tracked_candidate"
        ),
        "processing_allowed": True,
        "assumptions": ["Synthetic geometry exercises the consequence contract."],
    }


def _contract(tmp_path: Path, *, official: bool) -> dict[str, object]:
    raster = _write_raster(tmp_path / "probability.tif")
    roads = _write_geojson(tmp_path / "roads.geojson", kind="road_segments")
    facilities = _write_geojson(tmp_path / "facilities.geojson", kind="facilities")
    source = _source_metadata(official=official)
    return {
        "raster": raster,
        "roads": roads,
        "facilities": facilities,
        "source": source,
        "raster_receipt": _raster_receipt(source, raster),
        "road_receipt": _geometry_receipt(
            roads, kind="road_segments", authoritative=official
        ),
        "facility_receipt": _geometry_receipt(
            facilities, kind="facilities", authoritative=official
        ),
    }


def _create(contract: dict[str, object], **overrides: object) -> dict[str, object]:
    arguments: dict[str, object] = {
        "probability_raster_path": contract["raster"],
        "road_geometry_path": contract["roads"],
        "facility_geometry_path": contract["facilities"],
        "source_metadata": contract["source"],
        "probability_raster_receipt": contract["raster_receipt"],
        "road_geometry_receipt": contract["road_receipt"],
        "facility_geometry_receipt": contract["facility_receipt"],
        "road_buffer_distance_m": 10.0,
        "facility_buffer_distance_m": 15.0,
        "signing_key": KEY,
        "key_id": KEY_ID,
        "generated_at": GENERATED_AT,
    }
    arguments.update(overrides)
    return create_signed_consequence_receipt(**arguments)  # type: ignore[arg-type]


def _verify(
    receipt: dict[str, object], contract: dict[str, object]
) -> dict[str, object]:
    return verify_signed_consequence_receipt(
        receipt,
        probability_raster_path=contract["raster"],
        road_geometry_path=contract["roads"],
        facility_geometry_path=contract["facilities"],
        source_metadata=contract["source"],
        probability_raster_receipt=contract["raster_receipt"],
        road_geometry_receipt=contract["road_receipt"],
        facility_geometry_receipt=contract["facility_receipt"],
        signing_key=KEY,
        expected_key_id=KEY_ID,
    )


def test_official_probability_consequences_are_signed_and_semantically_bounded(
    tmp_path: Path,
) -> None:
    contract = _contract(tmp_path, official=True)
    receipt = _create(contract)

    assert receipt["can_feed_decision_layer"] is True
    assert receipt["study_area"] == "synthetic_contract_grid"
    assert receipt["aggregation_status"] == "decision_eligible"
    assert receipt["reason_blocked"] == ""
    assert receipt["signature"]["algorithm"] == "HMAC-SHA256"
    assert [row["road_id"] for row in receipt["roads"]] == [
        "ROAD-HIGH",
        "ROAD-LOW",
    ]
    high_road = receipt["roads"][0]
    assert high_road["modeled_exposure_status"] == (
        "modeled_probability_above_threshold"
    )
    assert high_road["bridge_probability_evidence_status"] == (
        "modeled_bridge_probability_above_threshold"
    )
    assert high_road["observed_closure_status"] == "not_observed"
    candidate_facility = receipt["facilities"][0]
    verified_facility = receipt["facilities"][1]
    assert candidate_facility["agency_verified_designated_role"] is False
    assert verified_facility["agency_verified_designated_role"] is True
    assert all(
        item["safe_destination_status"] == "not_determined_by_probability_model"
        for item in receipt["facilities"]
    )
    assert _verify(receipt, contract)["probability_raster_sha256"] == _sha(
        contract["raster"]
    )
    serialized = json.dumps(receipt)
    assert str(tmp_path) not in serialized
    assert KEY.decode("ascii") not in serialized


def test_candidate_probability_consequences_remain_explicitly_report_only(
    tmp_path: Path,
) -> None:
    contract = _contract(tmp_path, official=False)
    with pytest.raises(ProbabilityConsequenceError, match="not decision-eligible"):
        _create(contract)

    receipt = _create(contract, allow_report_only=True)
    assert receipt["dataset_mode"] == "candidate"
    assert receipt["official_warning"] is False
    assert receipt["can_feed_decision_layer"] is False
    assert receipt["aggregation_status"] == "report_only"
    assert "provenance_tracked_candidate" in receipt["reason_blocked"]
    assert all(not row["eligible_for_decision_layer"] for row in receipt["roads"])
    assert all(
        not row["eligible_for_decision_layer"] for row in receipt["facilities"]
    )
    _verify(receipt, contract)


@pytest.mark.parametrize("artifact", ["raster", "roads", "facilities"])
def test_consequence_verification_rejects_artifact_substitution(
    tmp_path: Path, artifact: str
) -> None:
    contract = _contract(tmp_path, official=True)
    receipt = _create(contract)
    path = contract[artifact]
    path.write_bytes(path.read_bytes() + b"substituted")

    with pytest.raises(ProbabilityConsequenceError, match="lineage|bytes|raster"):
        _verify(receipt, contract)


def test_consequence_receipt_rejects_signed_field_tampering(tmp_path: Path) -> None:
    contract = _contract(tmp_path, official=True)
    receipt = _create(contract)
    tampered = deepcopy(receipt)
    tampered["roads"][0]["observed_closure_status"] = "closed"

    with pytest.raises(ProbabilityConsequenceError, match="signature is invalid"):
        _verify(tampered, contract)


def test_consequence_adapter_rejects_grid_and_geometry_substitution(
    tmp_path: Path,
) -> None:
    contract = _contract(tmp_path, official=True)
    changed_grid = deepcopy(contract["raster_receipt"])
    changed_grid["grid"]["transform"][2] += 10.0
    with pytest.raises(ProbabilityAggregationError, match="transform"):
        _create(contract, probability_raster_receipt=changed_grid)

    wrong_crs = deepcopy(contract["road_receipt"])
    wrong_crs["crs"] = "EPSG:4326"
    with pytest.raises(ProbabilityConsequenceError, match="CRS"):
        _create(contract, road_geometry_receipt=wrong_crs)


@pytest.mark.parametrize(
    ("receipt_key", "argument_name"),
    [
        ("road_receipt", "road_geometry_receipt"),
        ("facility_receipt", "facility_geometry_receipt"),
    ],
)
def test_consequence_adapter_rejects_cross_study_area_geometry_receipts(
    tmp_path: Path,
    receipt_key: str,
    argument_name: str,
) -> None:
    contract = _contract(tmp_path, official=True)
    substituted = deepcopy(contract[receipt_key])
    substituted["study_area"] = "another_study_area"

    with pytest.raises(ProbabilityConsequenceError, match="study_area"):
        _create(contract, **{argument_name: substituted})


@pytest.mark.parametrize("receipt_key", ["road_receipt", "facility_receipt"])
def test_consequence_verifier_rejects_cross_study_area_receipt_substitution(
    tmp_path: Path,
    receipt_key: str,
) -> None:
    contract = _contract(tmp_path, official=True)
    signed = _create(contract)
    contract[receipt_key] = deepcopy(contract[receipt_key])
    contract[receipt_key]["study_area"] = "another_study_area"

    with pytest.raises(ProbabilityConsequenceError, match="study_area"):
        _verify(signed, contract)


def test_consequence_adapter_rejects_unprocessed_or_false_live_claims(
    tmp_path: Path,
) -> None:
    contract = _contract(tmp_path, official=False)
    source = deepcopy(contract["source"])
    source["official_warning"] = True
    receipt = _raster_receipt(source, contract["raster"])
    with pytest.raises(ProbabilityConsequenceError, match="official_warning=false"):
        _create(
            contract,
            source_metadata=source,
            probability_raster_receipt=receipt,
            allow_report_only=True,
        )

    source = deepcopy(contract["source"])
    source["processing_allowed"] = False
    receipt = _raster_receipt(source, contract["raster"])
    with pytest.raises(ProbabilityConsequenceError, match="processing_allowed=true"):
        _create(
            contract,
            source_metadata=source,
            probability_raster_receipt=receipt,
            allow_report_only=True,
        )


def test_consequence_adapter_requires_strict_feature_semantics(tmp_path: Path) -> None:
    contract = _contract(tmp_path, official=True)
    _write_geojson(contract["roads"], kind="road_segments", bad_bridge=True)
    contract["road_receipt"]["sha256"] = _sha(contract["roads"])

    with pytest.raises(ProbabilityConsequenceError, match="bridge_flag must be a boolean"):
        _create(contract)


def test_consequence_cli_writes_once_without_serializing_the_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = importlib.util.spec_from_file_location(
        "build_probability_consequences",
        ROOT / "scripts/build_probability_consequences.py",
    )
    assert spec is not None and spec.loader is not None
    consequence_cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(consequence_cli)
    contract = _contract(tmp_path, official=False)
    source_path = tmp_path / "model-run.json"
    raster_receipt_path = tmp_path / "probability-receipt.json"
    road_receipt_path = tmp_path / "roads-receipt.json"
    facility_receipt_path = tmp_path / "facilities-receipt.json"
    output_path = tmp_path / "consequences.json"
    for path, payload in (
        (source_path, contract["source"]),
        (raster_receipt_path, contract["raster_receipt"]),
        (road_receipt_path, contract["road_receipt"]),
        (facility_receipt_path, contract["facility_receipt"]),
    ):
        path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("FLOODGUARD_CONSEQUENCE_SIGNING_KEY", KEY.decode("ascii"))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_probability_consequences.py",
            "--probability-raster",
            str(contract["raster"]),
            "--model-run-manifest",
            str(source_path),
            "--probability-raster-receipt",
            str(raster_receipt_path),
            "--roads",
            str(contract["roads"]),
            "--road-geometry-receipt",
            str(road_receipt_path),
            "--facilities",
            str(contract["facilities"]),
            "--facility-geometry-receipt",
            str(facility_receipt_path),
            "--generated-at",
            GENERATED_AT,
            "--allow-report-only",
            "--output",
            str(output_path),
        ],
    )

    assert consequence_cli.main() == 0
    receipt = json.loads(output_path.read_text(encoding="utf-8"))
    assert receipt["aggregation_status"] == "report_only"
    assert KEY.decode("ascii") not in output_path.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="Refusing to overwrite"):
        consequence_cli.main()
