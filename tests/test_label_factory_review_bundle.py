from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

from floodguard.label_factory.event_registry import EventRecord, SourceAssetRecord
from floodguard.label_factory.human_roles import build_human_role_package
from floodguard.label_factory.processing_alignment import processing_assets_by_id
from floodguard.label_factory.review_bundle import (
    ReviewBundleError,
    ReviewPurpose,
    build_annotation_template,
    build_blinded_context_manifest,
    build_blinded_review_manifest,
    validate_review_human_role_gate,
    validate_static_review_context_against_governance,
    write_blinded_review_bundle,
)
from label_factory_processing_fixtures import synthetic_processing_receipt
from test_label_factory_human_roles import _passing_receipt, _request, _sha


def _queries() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "query_region_id": "TH-MAESAI-2024-09_UTM47N_10M_X00000_Y00000_R00_C00_S64",
                "tile_id": "TH-MAESAI-2024-09_UTM47N_10M_X00000_Y00000",
                "event_id": "TH-MAESAI-2024-09",
                "grid_id": "UTM47N_10M",
                "grid_contract_sha256": "c" * 64,
                "source_registry_sha256": "1" * 64,
                "processing_alignment_receipt_sha256": "6" * 64,
                "pre_source_asset_ids": "SYNTHETIC-S1-PRE",
                "event_source_asset_ids": "SYNTHETIC-S1-EVENT",
                "pre_product_ids": "SYNTHETIC_SENTINEL1_PRODUCT_PRE",
                "event_product_ids": "SYNTHETIC_SENTINEL1_PRODUCT_EVENT",
                "pre_acquisition_utc": "2024-09-06T11:31:06Z",
                "event_acquisition_utc": "2024-09-15T23:16:01Z",
                "pre_source_sha256s": "a" * 64,
                "event_source_sha256s": "b" * 64,
                "feature_schema_version": "sar_change_v2",
                "query_size_pixels": 64,
                "resolution_m": 10.0,
                "bbox_min_x": 590000.0,
                "bbox_min_y": 2264000.0,
                "bbox_max_x": 590640.0,
                "bbox_max_y": 2264640.0,
                "crs": "EPSG:32647",
                "dataset_role": "training_and_query_pool",
                "review_status": "pending_manual_review",
                "eligible_for_human_annotation": True,
                "eligible_for_active_selection": True,
                "eligible_for_review_queue": True,
                "query_model_only": True,
                "eligible_for_decision_layer": False,
                "eligible_for_fpps": False,
                "eligible_for_warning": False,
                "source_timestamp": "2024-09-15T23:16:01Z",
                "confidence_class": "low",
                "assumptions": "Candidate review region; not a flood observation.",
                "selected": True,
                "mean_logistic_probability": 0.51,
                "mean_boosted_probability": 0.89,
                "entropy_p90": 0.95,
                "selection_score": 0.99,
                "selection_reason": "model disagreement",
                "weak_reference_fraction": 0.75,
            }
        ]
    )


def _context_layers(
    processing_receipt: dict[str, object] | None = None,
) -> pd.DataFrame:
    roles = (
        ("pre_event_vv", "PRE", "2024-09-06T11:31:06Z", "c"),
        ("pre_event_vh", "PRE", "2024-09-06T11:31:06Z", "d"),
        ("event_time_vv", "EVENT", "2024-09-15T23:16:01Z", "e"),
        ("event_time_vh", "EVENT", "2024-09-15T23:16:01Z", "f"),
        ("permanent_water_context", "PERMANENT", "2021-01-01T00:00:00Z", "0"),
        ("land_cover", "LAND", "2021-01-01T00:00:00Z", "2"),
        ("dem_hillshade", "DEM", "2021-01-01T00:00:00Z", "3"),
    )
    processed_assets = (
        processing_assets_by_id(processing_receipt)
        if processing_receipt is not None
        else {}
    )
    return pd.DataFrame(
        [
            {
                "context_layer_id": f"SYNTHETIC-CTX-{role.upper()}",
                "event_id": "TH-MAESAI-2024-09",
                "layer_role": role,
                "source_registry_sha256": "1" * 64,
                "source_asset_id": f"SYNTHETIC-S1-{product}",
                "source_product_id": f"SYNTHETIC_SENTINEL1_PRODUCT_{product}",
                "display_name": f"Synthetic {role} fixed stretch",
                "path_hint": f"synthetic_review/{role}.tif",
                "crs": "EPSG:32647",
                "acquisition_time_utc": acquisition,
                "source_sha256": {
                    "PRE": "a",
                    "EVENT": "b",
                    "PERMANENT": "7",
                    "LAND": "8",
                    "DEM": "9",
                }[product]
                * 64,
                "processed_layer_sha256": (
                    processed_assets[f"SYNTHETIC-S1-{product}"][
                        "processed_file_sha256"
                    ]
                    if product in {"PRE", "EVENT"} and processed_assets
                    else processed_hash_character * 64
                ),
                "allowed_for_blinded_review": True,
                "confidence_class": "low",
                "assumptions": (
                    "Synthetic provenance fixture only; no real imagery or flood truth."
                ),
            }
            for role, product, acquisition, processed_hash_character in roles
        ]
    )


def _non_acquisition_queries(dataset_role: str) -> pd.DataFrame:
    queries = _queries().copy()
    queries["dataset_role"] = dataset_role
    queries["eligible_for_review_queue"] = False
    queries["eligible_for_active_selection"] = False
    queries["selected"] = False
    return queries.drop(
        columns=[
            "mean_logistic_probability",
            "mean_boosted_probability",
            "entropy_p90",
            "selection_score",
            "selection_reason",
        ]
    )


def _processing_receipt(tmp_path: Path) -> dict[str, object]:
    event = EventRecord.from_mapping(
        {
            "event_id": "TH-MAESAI-2024-09",
            "event_name": "Synthetic review-bundle processing fixture",
            "country": "Thailand",
            "study_area": "Synthetic projected bounds only",
            "event_start_utc": "2024-09-10T00:00:00Z",
            "event_end_utc": "2024-09-16T00:00:00Z",
            "pre_acquisition_utc": "2024-09-06T11:31:06Z",
            "post_acquisition_utc": "2024-09-15T23:16:01Z",
            "analysis_crs": "EPSG:32647",
            "analysis_resolution_m": 10,
            "grid_origin_x": 590000,
            "grid_origin_y": 2264000,
            "tile_size_pixels": 256,
            "query_size_pixels": 64,
            "dataset_role": "training_and_query_pool",
            "label_status": "unreviewed",
            "source_rights_status": "confirmed",
            "processing_allowed": True,
            "ml_label_derivation_allowed": True,
            "validation_allowed": True,
            "source_timestamp": "2024-09-20T00:00:00Z",
            "confidence_class": "low",
            "assumptions": "Synthetic review-bundle fixture; no real processing.",
        }
    )
    sources = tuple(
        SourceAssetRecord.from_mapping(
            {
                "asset_id": f"SYNTHETIC-S1-{role_name}",
                "event_id": event.event_id,
                "sensor": "SAR",
                "platform": "Sentinel-1",
                "product_id": f"SYNTHETIC_SENTINEL1_PRODUCT_{role_name}",
                "acquisition_time_utc": acquisition,
                "event_relative_role": role,
                "orbit_direction": "descending",
                "relative_orbit": "142",
                "polarizations": "VV,VH",
                "processing_level": "synthetic_source_fixture",
                "crs": event.analysis_crs,
                "pixel_spacing_m": 10,
                "local_path_hint": f"outside_git/{role_name}.tif",
                "sha256": hash_character * 64,
                "sha256_status": "recorded",
                "license_status": "confirmed",
                "processing_allowed": True,
                "ml_label_derivation_allowed": True,
                "redistribution_status": "reference_only",
                "georegistration_method": "synthetic_fixture",
                "georegistration_error_pixels": 0.25,
                "source_timestamp": "2024-09-20T00:00:00Z",
                "confidence_class": "low",
                "assumptions": "Synthetic source fixture; no real imagery.",
            }
        )
        for role_name, role, acquisition, hash_character in (
            ("PRE", "pre_event", "2024-09-06T11:31:06Z", "a"),
            ("EVENT", "event_time", "2024-09-15T23:16:01Z", "b"),
        )
    )
    return synthetic_processing_receipt(tmp_path, [event], list(sources))


def _queries_bound_to(
    queries: pd.DataFrame,
    receipt: dict[str, object],
) -> pd.DataFrame:
    bound = queries.copy()
    bound["processing_alignment_receipt_sha256"] = receipt["receipt_sha256"]
    bound["grid_contract_sha256"] = receipt["assets"][0][
        "grid_contract_sha256"
    ]
    return bound


def test_blinded_manifest_removes_model_and_weak_label_evidence() -> None:
    review = build_blinded_review_manifest(
        _queries(), review_purpose=ReviewPurpose.ACQUISITION_PRIMARY
    )

    assert len(review) == 1
    assert "geometry_wkt" in review.columns
    assert review.loc[0, "geometry_wkt"].startswith("POLYGON")
    assert "mean_logistic_probability" not in review.columns
    assert "entropy_p90" not in review.columns
    assert "selection_reason" not in review.columns
    assert "weak_reference_fraction" not in review.columns
    assert review.loc[0, "review_purpose"] == "acquisition_primary"
    assert review.loc[0, "source_registry_sha256"] == "1" * 64
    assert review.loc[0, "pre_product_ids"] == "SYNTHETIC_SENTINEL1_PRODUCT_PRE"


def test_blinded_manifest_preserves_complete_supported_query_lineage() -> None:
    queries = _queries()
    queries["supported_query_allowlist_applied"] = True
    queries["supported_query_derivation_sha256"] = "d" * 64
    queries["supported_query_csv_sha256"] = "e" * 64

    review = build_blinded_review_manifest(
        queries,
        review_purpose=ReviewPurpose.ACQUISITION_PRIMARY,
    )

    assert review.loc[0, "supported_query_allowlist_applied"] == True
    assert review.loc[0, "supported_query_derivation_sha256"] == "d" * 64
    assert review.loc[0, "supported_query_csv_sha256"] == "e" * 64

    partial = queries.drop(columns=["supported_query_csv_sha256"])
    with pytest.raises(ReviewBundleError, match="lineage is partial"):
        build_blinded_review_manifest(
            partial,
            review_purpose=ReviewPurpose.ACQUISITION_PRIMARY,
        )


def test_annotation_template_preserves_unreviewed_semantics() -> None:
    review = build_blinded_review_manifest(
        _queries(), review_purpose=ReviewPurpose.ACQUISITION_PRIMARY
    )
    template = build_annotation_template(review)

    assert template.loc[0, "reviewer_id"] == ""
    assert template.loc[0, "primary_class"] == ""
    assert template.loc[0, "geometry_wkt"] == ""
    assert template.loc[0, "reviewed_extent_status"] == "not_reviewed"
    assert template.loc[0, "reviewed_extent"] == ""
    assert template.loc[0, "review_stage"] == "primary"
    assert template.loc[0, "review_purpose"] == "acquisition_primary"
    assert template.loc[0, "model_predictions_visible"] == False
    assert template.loc[0, "other_reviewer_annotations_visible"] == False
    assert template.loc[0, "created_at_utc"] == ""
    assert template.loc[0, "locked_at_utc"] == ""
    assert "not dry land" in template.loc[0, "assumptions"]


def test_secondary_bundle_is_explicit_and_still_blinded() -> None:
    review = build_blinded_review_manifest(
        _queries(), review_purpose=ReviewPurpose.ACQUISITION_PRIMARY
    )
    template = build_annotation_template(review, review_stage="secondary")

    assert template.loc[0, "review_stage"] == "secondary"
    assert template.loc[0, "model_predictions_visible"] == False
    assert template.loc[0, "other_reviewer_annotations_visible"] == False


def test_review_bundle_rejects_any_decision_layer_eligibility() -> None:
    queries = _queries()
    queries.loc[0, "eligible_for_decision_layer"] = True

    with pytest.raises(ReviewBundleError, match="forbidden eligibility"):
        build_blinded_review_manifest(
            queries, review_purpose=ReviewPurpose.ACQUISITION_PRIMARY
        )


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("dataset_role", "untouched_geographic_test", "not allowed"),
        ("review_status", "already_reviewed", "not unreviewed"),
        ("eligible_for_fpps", "garbage", "explicit boolean"),
        ("eligible_for_human_annotation", False, "not eligible for human annotation"),
        ("eligible_for_active_selection", False, "active-selection eligibility"),
        ("source_timestamp", "not-a-time", "invalid source_timestamp"),
        ("confidence_class", "garbage", "invalid confidence_class"),
        ("crs", "EPSG:4326", "not projected"),
    ],
)
def test_review_bundle_rejects_role_status_and_metadata_garbage(
    column: str, value: object, message: str
) -> None:
    queries = _queries()
    if column == "eligible_for_fpps":
        queries[column] = queries[column].astype(object)
    queries.loc[0, column] = value

    with pytest.raises(ReviewBundleError, match=message):
        build_blinded_review_manifest(
            queries, review_purpose=ReviewPurpose.ACQUISITION_PRIMARY
        )


def test_review_purpose_isolates_calibration_and_fixed_evaluation_roles() -> None:
    calibration = build_blinded_review_manifest(
        _non_acquisition_queries("reviewer_calibration"),
        review_purpose=ReviewPurpose.REVIEWER_CALIBRATION,
    )
    assert calibration["dataset_role"].eq("reviewer_calibration").all()
    assert calibration["review_purpose"].eq("reviewer_calibration").all()

    development = _non_acquisition_queries("fixed_within_event_development")
    geographic_test = _non_acquisition_queries("untouched_geographic_test")
    geographic_test["query_region_id"] = geographic_test["query_region_id"] + "-TEST"
    fixed = build_blinded_review_manifest(
        pd.concat([development, geographic_test], ignore_index=True),
        review_purpose=ReviewPurpose.FIXED_EVALUATION,
    )
    assert set(fixed["dataset_role"]) == {
        "fixed_within_event_development",
        "untouched_geographic_test",
    }
    assert fixed["review_purpose"].eq("fixed_evaluation").all()


def _frozen_human_role_package(tmp_path: Path, *, formal: bool) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    request, evidence_root = _request(tmp_path)
    output = tmp_path / ("human-roles-formal" if formal else "human-roles-precalibration")
    if formal:
        calibration_receipt = _passing_receipt(tmp_path / "passing-calibration.json")
        request["formal_review_authorization_requested"] = True
        request["calibration_receipt_file_sha256"] = _sha(calibration_receipt)
        build_human_role_package(
            request,
            evidence_root=evidence_root,
            output_dir=output,
            calibration_receipt_path=calibration_receipt,
        )
    else:
        build_human_role_package(
            request,
            evidence_root=evidence_root,
            output_dir=output,
        )
    return output


def test_calibration_bundle_binds_precalibration_package_and_reviewer(
    tmp_path: Path,
) -> None:
    human_roles = _frozen_human_role_package(tmp_path / "roles", formal=False)
    receipt = _processing_receipt(tmp_path / "processing")
    written = write_blinded_review_bundle(
        _queries_bound_to(_non_acquisition_queries("reviewer_calibration"), receipt),
        tmp_path / "calibration-bundle",
        review_purpose=ReviewPurpose.REVIEWER_CALIBRATION,
        processing_alignment_receipt=receipt,
        allow_ungoverned_fixture=True,
        context_layers=_context_layers(receipt),
        human_role_package=human_roles,
        target_reviewer_id="FG-RV-A-001",
        planned_review_start_utc="2024-09-17T00:00:00Z",
    )

    template = pd.read_csv(written["annotation_template"], keep_default_na=False)
    manifest = pd.read_csv(written["bundle_manifest"], keep_default_na=False)
    assert template["reviewer_id"].eq("FG-RV-A-001").all()
    assert manifest["human_role_package_id"].eq("mae_sai_human_roles_v1").all()
    assert manifest["human_role_package_manifest_sha256"].str.len().eq(64).all()
    assert manifest["human_role_binding_status"].eq(
        "precalibration_appointments_frozen"
    ).all()
    assert manifest["human_role_formal_review_authorized"].eq(False).all()
    assert manifest["target_reviewer_role_category"].eq("reviewer_a").all()


def test_formal_role_gate_requires_passing_package_exact_lane_and_time(
    tmp_path: Path,
) -> None:
    formal = _frozen_human_role_package(tmp_path / "formal", formal=True)
    binding = validate_review_human_role_gate(
        formal,
        review_purpose=ReviewPurpose.ACQUISITION_PRIMARY,
        review_stage="secondary",
        target_reviewer_id="FG-RV-B-001",
        planned_review_start_utc="2024-09-17T00:00:00Z",
        event_id="TH-MAESAI-2024-09",
    )
    assert binding["human_role_binding_status"] == "formal_review_authorized"
    assert binding["human_role_formal_review_authorized"] is True
    assert binding["formal_review_authorized_from_utc"] == "2024-09-16T00:30:00Z"
    assert len(str(binding["calibration_receipt_sha256"])) == 64

    with pytest.raises(ReviewBundleError, match="not the appointed reviewer_b"):
        validate_review_human_role_gate(
            formal,
            review_purpose=ReviewPurpose.ACQUISITION_PRIMARY,
            review_stage="secondary",
            target_reviewer_id="FG-RV-A-001",
            planned_review_start_utc="2024-09-17T00:00:00Z",
            event_id="TH-MAESAI-2024-09",
        )
    with pytest.raises(ReviewBundleError, match="formal_review_authorized_from_utc"):
        validate_review_human_role_gate(
            formal,
            review_purpose=ReviewPurpose.ACQUISITION_PRIMARY,
            review_stage="primary",
            target_reviewer_id="FG-RV-A-001",
            planned_review_start_utc="2024-09-16T00:00:00Z",
            event_id="TH-MAESAI-2024-09",
        )


def test_role_gate_keeps_calibration_and_formal_packages_separate(
    tmp_path: Path,
) -> None:
    precalibration = _frozen_human_role_package(tmp_path / "pre", formal=False)
    formal = _frozen_human_role_package(tmp_path / "post", formal=True)

    with pytest.raises(ReviewBundleError, match="formal_review_authorized=true"):
        validate_review_human_role_gate(
            precalibration,
            review_purpose=ReviewPurpose.ACQUISITION_PRIMARY,
            review_stage="primary",
            target_reviewer_id="FG-RV-A-001",
            planned_review_start_utc="2024-09-17T00:00:00Z",
            event_id="TH-MAESAI-2024-09",
        )
    with pytest.raises(ReviewBundleError, match="pre-calibration human-role package"):
        validate_review_human_role_gate(
            formal,
            review_purpose=ReviewPurpose.REVIEWER_CALIBRATION,
            review_stage="primary",
            target_reviewer_id="FG-RV-A-001",
            planned_review_start_utc="2024-09-17T00:00:00Z",
            event_id="TH-MAESAI-2024-09",
        )
    with pytest.raises(ReviewBundleError, match="pre-calibration package not-before"):
        validate_review_human_role_gate(
            precalibration,
            review_purpose=ReviewPurpose.REVIEWER_CALIBRATION,
            review_stage="primary",
            target_reviewer_id="FG-RV-A-001",
            planned_review_start_utc="2024-09-16T23:59:59Z",
            event_id="TH-MAESAI-2024-09",
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"event_id": "TH-OTHER-EVENT"}, "event_id"),
        ({"protocol_version": "label_factory_protocol_v999"}, "protocol_version"),
        ({"taxonomy_version": "flood_label_v999"}, "taxonomy_version"),
    ],
)
def test_role_gate_binds_event_protocol_and_taxonomy(
    tmp_path: Path,
    overrides: dict[str, str],
    message: str,
) -> None:
    formal = _frozen_human_role_package(tmp_path, formal=True)
    arguments = {
        "review_purpose": ReviewPurpose.ACQUISITION_PRIMARY,
        "review_stage": "primary",
        "target_reviewer_id": "FG-RV-A-001",
        "planned_review_start_utc": "2024-09-17T00:00:00Z",
        "event_id": "TH-MAESAI-2024-09",
        "protocol_version": "label_factory_protocol_v1",
        "taxonomy_version": "flood_label_v1",
        **overrides,
    }

    with pytest.raises(ReviewBundleError, match=message):
        validate_review_human_role_gate(formal, **arguments)


@pytest.mark.parametrize(
    ("dataset_role", "review_purpose"),
    [
        ("reviewer_calibration", ReviewPurpose.REVIEWER_CALIBRATION),
        ("fixed_within_event_development", ReviewPurpose.FIXED_EVALUATION),
        ("untouched_geographic_test", ReviewPurpose.FIXED_EVALUATION),
    ],
)
def test_formal_non_acquisition_bundles_record_role_and_purpose(
    tmp_path: Path,
    dataset_role: str,
    review_purpose: ReviewPurpose,
) -> None:
    receipt = _processing_receipt(tmp_path / "processing")
    written = write_blinded_review_bundle(
        _queries_bound_to(_non_acquisition_queries(dataset_role), receipt),
        tmp_path / dataset_role,
        review_purpose=review_purpose,
        processing_alignment_receipt=receipt,
        allow_ungoverned_fixture=True,
        context_layers=_context_layers(receipt),
    )

    regions = pd.read_csv(written["review_regions"])
    template = pd.read_csv(written["annotation_template"])
    bundle_manifest = pd.read_csv(written["bundle_manifest"])
    assert regions["dataset_role"].eq(dataset_role).all()
    assert regions["review_purpose"].eq(review_purpose.value).all()
    assert template["review_purpose"].eq(review_purpose.value).all()
    assert bundle_manifest["review_purpose"].eq(review_purpose.value).all()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("selected", True),
        ("active_score", 0.99),
        ("selection_lane", "active"),
        ("mean_logistic_probability", 0.75),
    ],
)
def test_fixed_evaluation_cannot_be_activated_by_selection_output(
    field: str, value: object
) -> None:
    queries = _non_acquisition_queries("untouched_geographic_test")
    queries[field] = value

    with pytest.raises(ReviewBundleError, match="cannot (consume|contain)"):
        build_blinded_review_manifest(
            queries,
            review_purpose=ReviewPurpose.FIXED_EVALUATION,
        )


def test_custom_selection_column_cannot_hide_active_test_selection() -> None:
    queries = _non_acquisition_queries("untouched_geographic_test")
    queries["selected"] = True
    queries["fixed_membership"] = False

    with pytest.raises(ReviewBundleError, match="activated by a selected flag"):
        build_blinded_review_manifest(
            queries,
            review_purpose=ReviewPurpose.FIXED_EVALUATION,
            selected_column="fixed_membership",
        )


def test_review_purpose_rejects_cross_role_use() -> None:
    queries = _non_acquisition_queries("untouched_geographic_test")

    with pytest.raises(ReviewBundleError, match="not allowed"):
        build_blinded_review_manifest(
            queries,
            review_purpose=ReviewPurpose.REVIEWER_CALIBRATION,
        )


def test_write_review_bundle_records_hashes_and_no_model_fields(tmp_path: Path) -> None:
    receipt = _processing_receipt(tmp_path / "processing")
    written = write_blinded_review_bundle(
        _queries_bound_to(_queries(), receipt),
        tmp_path / "bundle",
        review_purpose=ReviewPurpose.ACQUISITION_PRIMARY,
        processing_alignment_receipt=receipt,
        allow_ungoverned_fixture=True,
        context_layers=_context_layers(receipt),
    )

    assert set(written) == {
        "review_regions",
        "annotation_template",
        "instructions",
        "bundle_manifest",
        "context_layers",
        "processing_alignment_receipt",
    }
    visible = pd.read_csv(written["review_regions"])
    manifest = pd.read_csv(written["bundle_manifest"])
    assert "selection_score" not in visible.columns
    assert manifest["sha256"].str.len().eq(64).all()
    assert manifest["eligible_for_fpps"].eq(False).all()
    assert manifest["review_purpose"].eq("acquisition_primary").all()
    assert manifest["governance_binding_status"].eq(
        "synthetic_fixture_only"
    ).all()
    assert manifest["human_role_binding_status"].eq(
        "synthetic_fixture_only"
    ).all()
    assert manifest["target_reviewer_id"].fillna("").eq("").all()
    assert manifest["production_review_eligible"].eq(False).all()
    assert manifest["processing_alignment_receipt_sha256"].eq(
        receipt["receipt_sha256"]
    ).all()
    with pytest.raises(ReviewBundleError, match="already exists"):
        write_blinded_review_bundle(
            _queries_bound_to(_queries(), receipt),
            tmp_path / "bundle",
            review_purpose=ReviewPurpose.ACQUISITION_PRIMARY,
            processing_alignment_receipt=receipt,
            allow_ungoverned_fixture=True,
            context_layers=_context_layers(receipt),
        )


def test_synthetic_escape_rejects_partial_human_role_binding(tmp_path: Path) -> None:
    receipt = _processing_receipt(tmp_path / "processing")
    target = tmp_path / "partial-role-binding"

    with pytest.raises(ReviewBundleError, match="complete frozen human-role binding"):
        write_blinded_review_bundle(
            _queries_bound_to(_queries(), receipt),
            target,
            review_purpose=ReviewPurpose.ACQUISITION_PRIMARY,
            processing_alignment_receipt=receipt,
            allow_ungoverned_fixture=True,
            context_layers=_context_layers(receipt),
            target_reviewer_id="FG-RV-A-001",
        )

    assert not target.exists()


def test_production_derivative_context_remains_blocked_without_release(
    tmp_path: Path,
) -> None:
    receipt = _processing_receipt(tmp_path / "processing")
    target = tmp_path / "pending-derivative"

    with pytest.raises(ReviewBundleError, match="canonical derivative-context release"):
        write_blinded_review_bundle(
            _queries_bound_to(_queries(), receipt),
            target,
            review_purpose=ReviewPurpose.ACQUISITION_PRIMARY,
            processing_alignment_receipt=receipt,
            context_layers=_context_layers(receipt),
            derivative_lineage_receipt={},
        )

    assert not target.exists()


def test_production_cli_requires_human_role_binding_without_fixture_escape() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "build_label_factory_review_bundle.py"),
            "--help",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--human-role-package" in result.stdout
    assert "--target-reviewer-id" in result.stdout
    assert "--planned-review-start-utc" in result.stdout
    assert "--allow-ungoverned-fixture" not in result.stdout


def test_formal_bundle_requires_governance_and_leaves_no_residue(
    tmp_path: Path,
) -> None:
    receipt = _processing_receipt(tmp_path / "processing")
    target = tmp_path / "ungoverned" / "bundle"

    with pytest.raises(ReviewBundleError, match="governance-package"):
        write_blinded_review_bundle(
            _queries_bound_to(_queries(), receipt),
            target,
            review_purpose=ReviewPurpose.ACQUISITION_PRIMARY,
            processing_alignment_receipt=receipt,
            context_layers=_context_layers(receipt),
        )

    assert not target.exists()
    assert not target.parent.exists()


def test_static_context_is_bound_to_governed_inventory(tmp_path: Path) -> None:
    context = _context_layers()
    static = context.loc[
        context["layer_role"].isin(
            {"permanent_water_context", "land_cover", "dem_hillshade"}
        )
    ]
    inventory_rows = []
    for row in static.to_dict(orient="records"):
        inventory_rows.append(
            {
                "context_layer_id": row["context_layer_id"],
                "event_id": row["event_id"],
                "layer_role": row["layer_role"],
                "processed_path_hint": row["path_hint"],
                "processed_sha256": row["processed_layer_sha256"],
                "source_sha256s": f"source:{row['source_sha256']}",
                "output_crs": row["crs"],
                "allowed_for_blinded_review_candidate": True,
                "eligible_for_current_context_layers_csv": True,
                "rights_review_status": "approved_with_provider_conditions",
                "processing_allowed": True,
                "ml_label_derivation_allowed": True,
                "query_model_only": True,
                "eligible_for_decision_layer": False,
                "eligible_for_fpps": False,
                "eligible_for_warning": False,
            }
        )
    package = tmp_path / "governance_cleared_v9"
    package.mkdir()
    pd.DataFrame(inventory_rows).to_csv(
        package / "aligned_context_inventory.csv",
        index=False,
    )

    validate_static_review_context_against_governance(context, package)

    mismatched = context.copy()
    mismatched.loc[
        mismatched["layer_role"].eq("land_cover"), "processed_layer_sha256"
    ] = "f" * 64
    with pytest.raises(ReviewBundleError, match="governed inventory"):
        validate_static_review_context_against_governance(mismatched, package)


def test_context_manifest_allows_only_blinded_review_evidence() -> None:
    review = build_blinded_review_manifest(
        _queries(), review_purpose=ReviewPurpose.ACQUISITION_PRIMARY
    )
    context = _context_layers()
    context["logistic_probability"] = 0.99
    context["weak_label"] = 1

    visible = build_blinded_context_manifest(context, review)
    assert visible.loc[0, "layer_role"] == "pre_event_vv"
    assert "logistic_probability" not in visible
    assert "weak_label" not in visible

    context.loc[0, "layer_role"] = "logistic_prediction"
    with pytest.raises(ReviewBundleError, match="not approved"):
        build_blinded_context_manifest(context, review)

    derived = _context_layers()
    derived.loc[0, "layer_role"] = "vv_change"
    with pytest.raises(ReviewBundleError, match="derivative-lineage receipt"):
        build_blinded_context_manifest(derived, review)

    for unsafe_path in (r"\\server\share\layer.tif", "../secret.tif", "~/layer.tif", "file://layer.tif"):
        unsafe = context.copy()
        unsafe.loc[0, "layer_role"] = "pre_event_vv"
        unsafe.loc[0, "path_hint"] = unsafe_path
        with pytest.raises(ReviewBundleError, match="Unsafe context path_hint"):
            build_blinded_context_manifest(unsafe, review)


def test_write_bundle_can_include_hashed_context_references(tmp_path: Path) -> None:
    receipt = _processing_receipt(tmp_path / "processing")
    written = write_blinded_review_bundle(
        _queries_bound_to(_queries(), receipt),
        tmp_path / "context-bundle",
        review_purpose=ReviewPurpose.ACQUISITION_PRIMARY,
        processing_alignment_receipt=receipt,
        allow_ungoverned_fixture=True,
        context_layers=_context_layers(receipt),
    )

    assert "context_layers" in written
    bundle_manifest = pd.read_csv(written["bundle_manifest"])
    assert "approved_context_source_evidence" in set(bundle_manifest["bundle_role"])
    assert "processing_alignment_provenance" in set(bundle_manifest["bundle_role"])


def test_formal_bundle_rejects_context_not_bound_to_processed_file(
    tmp_path: Path,
) -> None:
    receipt = _processing_receipt(tmp_path / "processing")
    context = _context_layers(receipt)
    context.loc[0, "processed_layer_sha256"] = "f" * 64

    with pytest.raises(ReviewBundleError, match="processing receipt"):
        write_blinded_review_bundle(
            _queries_bound_to(_queries(), receipt),
            tmp_path / "bad-processing-lineage",
            review_purpose=ReviewPurpose.ACQUISITION_PRIMARY,
            processing_alignment_receipt=receipt,
            allow_ungoverned_fixture=True,
            context_layers=context,
        )


def test_formal_bundle_requires_context_and_leaves_no_residue(tmp_path: Path) -> None:
    target = tmp_path / "not-created" / "bundle"
    receipt = _processing_receipt(tmp_path / "processing")

    with pytest.raises(ReviewBundleError, match="requires --context-layers"):
        write_blinded_review_bundle(
            _queries_bound_to(_queries(), receipt),
            target,
            review_purpose=ReviewPurpose.ACQUISITION_PRIMARY,
            processing_alignment_receipt=receipt,
            allow_ungoverned_fixture=True,
        )

    assert not target.exists()
    assert not target.parent.exists()


def test_context_requires_all_four_sar_roles_before_creating_temp_dir(
    tmp_path: Path,
) -> None:
    receipt = _processing_receipt(tmp_path / "processing")
    context = _context_layers(receipt).query("layer_role != 'event_time_vh'")
    target = tmp_path / "missing-role" / "bundle"

    with pytest.raises(ReviewBundleError, match="missing required SAR roles: event_time_vh"):
        write_blinded_review_bundle(
            _queries_bound_to(_queries(), receipt),
            target,
            review_purpose=ReviewPurpose.ACQUISITION_PRIMARY,
            processing_alignment_receipt=receipt,
            allow_ungoverned_fixture=True,
            context_layers=context,
        )

    assert not target.parent.exists()


@pytest.mark.parametrize(
    ("removed_roles", "message"),
    [
        ({"permanent_water_context"}, "missing required review context roles"),
        ({"dem_hillshade"}, "requires at least one terrain role"),
    ],
)
def test_context_requires_static_and_terrain_evidence(
    removed_roles: set[str],
    message: str,
) -> None:
    context = _context_layers().loc[
        lambda frame: ~frame["layer_role"].isin(removed_roles)
    ]
    review = build_blinded_review_manifest(
        _queries(), review_purpose=ReviewPurpose.ACQUISITION_PRIMARY
    )

    with pytest.raises(ReviewBundleError, match=message):
        build_blinded_context_manifest(context, review)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("source_product_id", "", "blank source_product_id"),
        ("source_product_id", "unknown", "exact source_product_id"),
        ("acquisition_time_utc", "", "blank acquisition_time_utc"),
        ("acquisition_time_utc", "2024-09-06T18:31:06+07:00", "ending in Z"),
        ("crs", "", "blank crs"),
        ("crs", "EPSG:32648", "CRS does not match"),
        ("source_sha256", "A" * 64, "invalid source_sha256"),
        ("processed_layer_sha256", "not-a-hash", "invalid processed_layer_sha256"),
        ("confidence_class", "", "invalid confidence_class"),
    ],
)
def test_context_source_evidence_metadata_is_fail_closed(
    field: str,
    value: object,
    message: str,
) -> None:
    context = _context_layers()
    context.loc[0, field] = value
    review = build_blinded_review_manifest(
        _queries(), review_purpose=ReviewPurpose.ACQUISITION_PRIMARY
    )

    with pytest.raises(ReviewBundleError, match=message):
        build_blinded_context_manifest(context, review)


@pytest.mark.parametrize("missing_column", ["source_product_id", "processed_layer_sha256"])
def test_context_source_evidence_requires_provenance_columns(
    missing_column: str,
) -> None:
    review = build_blinded_review_manifest(
        _queries(), review_purpose=ReviewPurpose.ACQUISITION_PRIMARY
    )

    with pytest.raises(ReviewBundleError, match=f"missing columns: {missing_column}"):
        build_blinded_context_manifest(
            _context_layers().drop(columns=[missing_column]),
            review,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("source_registry_sha256", "2" * 64, "does not match its selected queries"),
        ("source_asset_id", "SYNTHETIC-S1-WRONG", "not present"),
        ("source_product_id", "SYNTHETIC_SENTINEL1_PRODUCT_WRONG", "not present"),
        ("acquisition_time_utc", "2024-09-07T11:31:06Z", "does not match"),
        ("source_sha256", "9" * 64, "not present"),
    ],
)
def test_context_raw_sar_evidence_must_match_query_source_lineage(
    field: str,
    value: object,
    message: str,
) -> None:
    context = _context_layers()
    context.loc[0, field] = value
    review = build_blinded_review_manifest(
        _queries(), review_purpose=ReviewPurpose.ACQUISITION_PRIMARY
    )

    with pytest.raises(ReviewBundleError, match=message):
        build_blinded_context_manifest(context, review)


def test_context_source_checksum_must_match_query_lineage() -> None:
    context = _context_layers()
    context.loc[1, "source_sha256"] = "9" * 64
    review = build_blinded_review_manifest(
        _queries(), review_purpose=ReviewPurpose.ACQUISITION_PRIMARY
    )

    with pytest.raises(ReviewBundleError, match="not present in the selected queries"):
        build_blinded_context_manifest(context, review)


def test_context_event_and_bundle_crs_must_match_queries() -> None:
    review = build_blinded_review_manifest(
        _queries(), review_purpose=ReviewPurpose.ACQUISITION_PRIMARY
    )
    unexpected_event = _context_layers()
    unexpected_event.loc[0, "event_id"] = "TH-SYNTHETIC-OTHER-EVENT"
    with pytest.raises(ReviewBundleError, match="events outside"):
        build_blinded_context_manifest(unexpected_event, review)

    second_crs_query = _queries()
    second_crs_query["query_region_id"] = second_crs_query["query_region_id"] + "-B"
    second_crs_query["crs"] = "EPSG:32648"
    mixed_crs_review = pd.concat(
        [review, build_blinded_review_manifest(
            second_crs_query,
            review_purpose=ReviewPurpose.ACQUISITION_PRIMARY,
        )],
        ignore_index=True,
    )
    with pytest.raises(ReviewBundleError, match="exactly one projected CRS"):
        build_blinded_context_manifest(_context_layers(), mixed_crs_review)
