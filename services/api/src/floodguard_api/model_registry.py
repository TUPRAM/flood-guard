"""Deterministic, study-area-bound public model registry projections."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from floodguard_api.models import EvidenceContext, ModelRun
from floodguard_api.repository import ArtifactNotFound, ArtifactUnavailable
from floodguard_api.v2_models import (
    FloodObservationProductV2,
    ModelEvaluationV2,
    ModelRegistryEvidenceBundleV1,
    ModelRegistryPayloadV1,
    ModelRunV2,
    SignedModelRegistryEntryV1,
)

FIXTURE_STUDY_AREA = "fixture_thailand_demo"
MAE_SAI_STUDY_AREA = "mae_sai_candidate_v1"
FIXTURE_EVENT_ID = "fixture-synthetic-integration-2026"
MAE_SAI_EVENT_ID = "mae-sai-historic-2024-09"
PROJECTION_KEY_ID = "floodguard-public-projection-test-v1"
# Deliberately public and non-secret. This provides deterministic fixture
# integrity only; it is never promotion, field-validation, or agency authority.
PUBLIC_PROJECTION_TEST_KEY = (
    b"FloodGuard public deterministic projection fixture; non-authoritative v1"
)


class RegistryRepository(Protocol):
    """Minimum repository surface needed by the registry projection."""

    def evidence_context(self, study_area: str = FIXTURE_STUDY_AREA) -> EvidenceContext: ...

    def model_runs(self, study_area: str = FIXTURE_STUDY_AREA) -> list[ModelRun]: ...


@dataclass(frozen=True)
class RegistryProjectionBundle:
    """Canonical artifacts referenced by one signed registry entry."""

    model_run: ModelRunV2
    evaluation: ModelEvaluationV2
    product: FloodObservationProductV2
    entry: SignedModelRegistryEntryV1


def canonical_json(value: Any) -> bytes:
    """Serialize a public projection deterministically for hashing and signing."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_model_sha256(model: Any) -> str:
    """Hash the exact JSON-mode representation of one Pydantic projection."""

    return hashlib.sha256(
        canonical_json(model.model_dump(mode="json"))
    ).hexdigest()


def build_model_registry(
    repository: RegistryRepository,
    study_area: str,
    *,
    now: datetime | None = None,
) -> list[SignedModelRegistryEntryV1]:
    """Build and validate the only public registry entry for a study area.

    Validation is repeated after signing. Any source, study-area, model,
    evaluation, product, expiry, or signature mismatch fails closed with an
    ``ArtifactUnavailable`` response at the API boundary.
    """

    return [
        bundle.entry
        for bundle in build_model_registry_bundles(
            repository,
            study_area,
            now=now,
        )
    ]


def build_model_registry_bundles(
    repository: RegistryRepository,
    study_area: str,
    *,
    now: datetime | None = None,
) -> list[RegistryProjectionBundle]:
    """Build validated canonical evidence behind the public registry."""

    context = repository.evidence_context(study_area)
    scoped_runs = repository.model_runs(study_area)
    if study_area == FIXTURE_STUDY_AREA:
        bundle = _fixture_bundle(context, scoped_runs)
    elif study_area == MAE_SAI_STUDY_AREA:
        bundle = _mae_sai_bundle(context, scoped_runs)
    else:
        raise ArtifactNotFound(f"Unknown study_area: {study_area}")

    validate_registry_bundle(
        bundle,
        context=context,
        scoped_runs=scoped_runs,
        requested_study_area=study_area,
        now=now,
    )
    return [bundle]


def model_registry_entry(
    repository: RegistryRepository,
    registry_entry_id: str,
    study_area: str,
    *,
    now: datetime | None = None,
) -> SignedModelRegistryEntryV1:
    """Return a registry entry only inside its explicitly requested study area."""

    for entry in build_model_registry(repository, study_area, now=now):
        if entry.payload.registry_entry_id == registry_entry_id:
            return entry
    raise ArtifactNotFound(
        f"Unknown registry_entry_id for {study_area}: {registry_entry_id}"
    )


def model_registry_evidence(
    repository: RegistryRepository,
    registry_entry_id: str,
    study_area: str,
    *,
    now: datetime | None = None,
) -> ModelRegistryEvidenceBundleV1:
    """Return the exact validated v2 artifacts behind one registry entry."""

    context = repository.evidence_context(study_area)
    for bundle in build_model_registry_bundles(
        repository,
        study_area,
        now=now,
    ):
        if bundle.entry.payload.registry_entry_id != registry_entry_id:
            continue
        return ModelRegistryEvidenceBundleV1(
            evidence_context_id=context.evidence_context_id,
            source_bundle_sha256=context.evidence_package_sha256,
            entry=bundle.entry,
            model_run=bundle.model_run,
            evaluation=bundle.evaluation,
            product=bundle.product,
            official_warning=False,
            can_feed_decision_layer=False,
            reason_blocked=bundle.entry.payload.reason_blocked,
        )
    raise ArtifactNotFound(
        f"Unknown registry_entry_id for {study_area}: {registry_entry_id}"
    )


def validate_registry_bundle(
    bundle: RegistryProjectionBundle,
    *,
    context: EvidenceContext,
    scoped_runs: list[ModelRun],
    requested_study_area: str,
    now: datetime | None = None,
) -> None:
    """Reject any cross-context or digest substitution in a registry bundle."""

    payload = bundle.entry.payload
    signature = bundle.entry.signature
    current_time = (now or datetime.now(UTC)).astimezone(UTC)
    payload_bytes = canonical_json(payload.model_dump(mode="json"))
    payload_sha256 = hashlib.sha256(payload_bytes).hexdigest()
    expected_signature = hmac.new(
        PUBLIC_PROJECTION_TEST_KEY,
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()

    if signature.key_id != PROJECTION_KEY_ID:
        raise ArtifactUnavailable("Model registry projection key identity mismatch.")
    if not hmac.compare_digest(signature.payload_sha256, payload_sha256):
        raise ArtifactUnavailable("Model registry payload hash validation failed.")
    if not hmac.compare_digest(signature.value, expected_signature):
        raise ArtifactUnavailable("Model registry projection signature validation failed.")
    if requested_study_area != context.study_area_id:
        raise ArtifactUnavailable("Model registry request and evidence study area mismatch.")
    if payload.study_area_id != context.study_area_id:
        raise ArtifactUnavailable("Model registry entry study area substitution rejected.")
    if payload.source_bundle_sha256 != context.evidence_package_sha256:
        raise ArtifactUnavailable("Model registry source bundle substitution rejected.")
    if payload.dataset_mode != context.dataset_mode.value:
        raise ArtifactUnavailable(
            "Model registry dataset mode does not match its evidence context."
        )
    if payload.operational_status != context.operational_status.value:
        raise ArtifactUnavailable(
            "Model registry operational status does not match its evidence context."
        )
    if payload.expires_at.astimezone(UTC) <= current_time:
        raise ArtifactUnavailable("Model registry entry has expired and requires revalidation.")
    if payload.valid_from.astimezone(UTC) > current_time:
        raise ArtifactUnavailable("Model registry entry is not yet valid.")

    run_sha256 = canonical_model_sha256(bundle.model_run)
    evaluation_sha256 = canonical_model_sha256(bundle.evaluation)
    product_sha256 = canonical_model_sha256(bundle.product)
    model = bundle.model_run.model
    if (
        payload.model_run_id != bundle.model_run.run_id
        or payload.model_run_manifest_sha256 != run_sha256
        or payload.model_id != model.model_id
        or payload.model_sha256 != model.model_sha256
    ):
        raise ArtifactUnavailable("Model registry model-run binding validation failed.")
    if (
        payload.evaluation_id != bundle.evaluation.evaluation_id
        or payload.evaluation_manifest_sha256 != evaluation_sha256
        or payload.controlled_result_receipt_sha256
        != bundle.evaluation.controlled_result_receipt_sha256
        or bundle.evaluation.study_area_id != payload.study_area_id
        or bundle.evaluation.model_run_id != payload.model_run_id
        or bundle.evaluation.model_id != payload.model_id
        or bundle.evaluation.model_sha256 != payload.model_sha256
        or bundle.evaluation.model_run_manifest_sha256
        != payload.model_run_manifest_sha256
    ):
        raise ArtifactUnavailable("Model registry evaluation binding validation failed.")
    if (
        payload.product_id != bundle.product.product_id
        or payload.product_manifest_sha256 != product_sha256
        or bundle.product.study_area_id != payload.study_area_id
        or bundle.product.event_id != payload.event_id
        or bundle.product.evidence_kind != payload.evidence_kind
        or bundle.product.source_manifest_sha256 != payload.source_bundle_sha256
        or bundle.product.model_run_manifest_sha256
        != payload.model_run_manifest_sha256
        or bundle.product.model_sha256 != payload.model_sha256
        or bundle.product.evaluation_manifest_sha256
        != payload.evaluation_manifest_sha256
    ):
        raise ArtifactUnavailable("Model registry observation-product binding failed.")
    if any(
        (
            payload.official_warning,
            payload.can_feed_decision_layer,
            bundle.model_run.can_feed_decision_layer,
            bundle.evaluation.can_feed_decision_layer,
            bundle.product.can_feed_decision_layer,
            bundle.product.counts_as_observed_evidence,
        )
    ):
        raise ArtifactUnavailable("Candidate registry projection crossed a safety boundary.")

    if requested_study_area == FIXTURE_STUDY_AREA:
        if len(scoped_runs) != 1:
            raise ArtifactUnavailable(
                "Fixture registry requires exactly one scoped public model run."
            )
        public_run = scoped_runs[0]
        if (
            public_run.study_area != requested_study_area
            or public_run.run_id != payload.model_run_id
            or public_run.model_id != payload.model_id
            or public_run.model_sha256 != payload.model_sha256
            or public_run.can_feed_decision_layer
        ):
            raise ArtifactUnavailable(
                "Fixture registry does not exactly match its scoped v1 model projection."
            )
    else:
        if context.model_run_id is not None or scoped_runs:
            raise ArtifactUnavailable(
                "Mae Sai model evidence must remain unbound and cannot inherit another run."
            )
        if payload.registry_status != "blocked":
            raise ArtifactUnavailable("Mae Sai registry projection must remain blocked.")


def _fixture_bundle(
    context: EvidenceContext,
    scoped_runs: list[ModelRun],
) -> RegistryProjectionBundle:
    if context.study_area_id != FIXTURE_STUDY_AREA or len(scoped_runs) != 1:
        raise ArtifactUnavailable("Fixture model registry source is incomplete.")
    public_run = scoped_runs[0]
    if (
        public_run.run_id != "synthetic-sar-baseline-v1"
        or public_run.model_id is None
        or public_run.model_sha256 is None
    ):
        raise ArtifactUnavailable("Expected deterministic fixture model identity is unavailable.")

    event_id = FIXTURE_EVENT_ID
    generated_at = context.generated_at
    reason = (
        "Accepted as a deterministic candidate fixture for software-path testing only; "
        "it is not real-event accuracy evidence. The public projection signature is "
        "non-authoritative and promotion, field-validation, and agency receipts are absent."
    )
    label_hash = _label_sha256("fixture synthetic reference labels v2")
    input_hash = public_run.input_manifest_rows[0].sha256
    run = ModelRunV2(
        dataset_mode="fixture_demo",
        operational_status="non_operational",
        source_timestamp=public_run.source_timestamp,
        generated_at=generated_at,
        confidence_class="low",
        source_name="FloodGuard deterministic SAR threshold fixture",
        assumptions=[
            "Tiny synthetic integration fixture only; no Thailand event accuracy claim.",
            "The configured model digest identifies deterministic fixture logic, "
            "not learned weights.",
        ],
        data_version=public_run.data_version,
        git_commit=public_run.git_commit,
        run_id=public_run.run_id,
        study_area_id=context.study_area_id,
        event_id=event_id,
        evidence_kind="external_algorithmic_baseline",
        run_status="completed",
        model={
            "model_id": public_run.model_id,
            "model_revision": public_run.model_revision,
            "model_family": "deterministic_sar_baseline",
            "backend": "deterministic",
            "architecture": "deterministic_threshold",
            "encoder": None,
            "encoder_weights": None,
            "framework": "floodguard",
            "framework_version": "1.0",
            "framework_commit": public_run.git_commit,
            "model_sha256": public_run.model_sha256,
        },
        input_manifest_rows=[
            {
                "role": "synthetic_sar_table",
                "modality": "other_context",
                "product_id": public_run.input_manifest_rows[0].product_id,
                "sha256": input_hash,
                "source_timestamp": public_run.input_manifest_rows[0].source_timestamp,
                "processing_allowed": True,
            }
        ],
        feature_contract={
            "feature_schema_id": "sar-physical-db-change-v1",
            "value_domain": "physical_float32",
            "dtype": "float32",
            "channel_count": 4,
            "channel_names": [
                "pre_vv_db",
                "post_vv_db",
                "pre_vh_db",
                "post_vh_db",
            ],
            "preprocessing_sidecar_sha256": _label_sha256(
                "fixture deterministic SAR preprocessing sidecar v1"
            ),
            "feature_stack_sha256": input_hash,
        },
        target_contract={
            "class_schema_id": "temporary-flood-binary-v1",
            "classes": [
                {"index": 0, "name": "not_flooded", "training_role": "negative"},
                {"index": 1, "name": "temporary_flood", "training_role": "positive"},
                {"index": 255, "name": "unknown", "training_role": "ignore"},
            ],
            "reference_mask_status": "synthetic_fixture_only",
            "label_release_sha256": label_hash,
        },
        training_lineage={
            "input_manifest_sha256": _label_sha256(
                f"fixture input manifest:{input_hash}"
            ),
            "training_dataset_manifest_sha256": _label_sha256(
                "fixture training dataset manifest v2"
            ),
            "label_release_sha256": label_hash,
            "prepared_tile_manifest_sha256": _label_sha256(
                "fixture prepared tile manifest v2"
            ),
            "controlled_model_run_receipt_sha256": _label_sha256(
                "fixture controlled model run receipt v2"
            ),
            "threshold_selection_receipt_sha256": _label_sha256(
                "fixture threshold selection receipt v2"
            ),
            "calibration_receipt_sha256": _label_sha256(
                "fixture synthetic calibration receipt v2"
            ),
        },
        partition_contract={
            "partition_manifest_sha256": _label_sha256(
                "fixture partition manifest v2"
            ),
            "training_partition_sha256": _label_sha256("fixture train partition v2"),
            "calibration_partition_sha256": _label_sha256(
                "fixture calibration partition v2"
            ),
            "final_holdout_partition_sha256": _label_sha256(
                "fixture final holdout partition v2"
            ),
            "train_ids": ["fixture-train-001"],
            "calibration_ids": ["fixture-calibration-001"],
            "final_holdout_ids": ["fixture-holdout-001"],
        },
        inference_contract={
            "target_crs": "EPSG:4326",
            "resolution": [1.0, 1.0],
            "bounds": [0.0, 0.0, 3.0, 2.0],
            "tile_size": 3,
            "overlap": 0,
            "stride": 3,
            "batch_size": 1,
            "device": "cpu",
            "probability_threshold": public_run.probability_threshold,
        },
        processing_allowed=True,
        can_feed_decision_layer=False,
        reason_blocked=reason,
    )
    run_sha256 = canonical_model_sha256(run)
    metrics = public_run.validation_metrics
    evaluation = ModelEvaluationV2(
        dataset_mode="fixture_demo",
        operational_status="non_operational",
        source_timestamp=public_run.source_timestamp,
        generated_at=generated_at,
        confidence_class="low",
        source_name="FloodGuard synthetic integration evaluation",
        assumptions=[
            "Metrics describe five synthetic pixels and cannot estimate real-event performance.",
            "Synthetic final-holdout terminology verifies contract flow only.",
            "Selective prediction, OOD, and downstream decision-impact gates were not evaluated.",
        ],
        data_version=public_run.data_version,
        git_commit=public_run.git_commit,
        evaluation_id="fixture-sar-baseline-evaluation-v2",
        experiment_id="fixture-sar-integration-v2",
        study_area_id=context.study_area_id,
        event_ids=[event_id],
        model_run_id=run.run_id,
        model_id=run.model.model_id,
        model_sha256=run.model.model_sha256,
        model_run_manifest_sha256=run_sha256,
        controlled_result_receipt_sha256=_label_sha256(
            "fixture controlled result receipt v2"
        ),
        evaluation_status="blocked",
        evaluation_scope="final_holdout",
        reference_evidence={
            "reference_mask_status": "synthetic_fixture_only",
            "reference_mask_sha256": label_hash,
            "label_release_sha256": label_hash,
            "reviewer_qualification_receipt_sha256": _label_sha256(
                "fixture synthetic reviewer receipt v2"
            ),
        },
        partition_evidence={
            "partition_manifest_sha256": run.partition_contract.partition_manifest_sha256,
            "training_partition_sha256": run.partition_contract.training_partition_sha256,
            "calibration_partition_sha256": (
                run.partition_contract.calibration_partition_sha256
            ),
            "final_holdout_partition_sha256": (
                run.partition_contract.final_holdout_partition_sha256
            ),
        },
        threshold_evidence={
            "threshold": public_run.probability_threshold,
            "threshold_selection_receipt_sha256": (
                run.training_lineage.threshold_selection_receipt_sha256
            ),
            "selection_scope": "verified_calibration_projection_only",
            "final_holdout_evaluated_during_selection": False,
        },
        overall_metrics={
            "sample_count": 5,
            "true_positive": 2,
            "false_positive": 1,
            "false_negative": 1,
            "true_negative": 1,
            "iou": metrics.iou,
            "f1_dice": metrics.f1_dice,
            "precision": metrics.precision,
            "recall": metrics.recall,
            "boundary_f1": metrics.f1_dice,
            "signed_area_error_ratio": 0.0,
            "absolute_area_error_ratio": metrics.area_error_ratio,
            "brier_score": metrics.brier_score,
            "negative_log_likelihood": 5.8,
            "expected_calibration_error": 0.3828,
        },
        event_metrics=[
            {
                "event_id": event_id,
                "sample_count": 5,
                "iou": metrics.iou,
                "f1_dice": metrics.f1_dice,
                "precision": metrics.precision,
                "recall": metrics.recall,
                "absolute_area_error_ratio": metrics.area_error_ratio,
                "brier_score": metrics.brier_score,
                "expected_calibration_error": 0.3828,
            }
        ],
        error_strata=[
            {
                "category": "synthetic_fixture_only",
                "coverage_status": "measured",
                "cell_count": 5,
                "false_positive_count": 1,
                "false_negative_count": 1,
                "precision": metrics.precision,
                "recall": metrics.recall,
            }
        ],
        calibration={
            "status": "evaluated",
            "method": "synthetic identity projection only",
            "reliability_asset_sha256": _label_sha256(
                "fixture reliability projection v2"
            ),
        },
        selective_prediction={
            "status": "not_evaluated",
            "risk_coverage_asset_sha256": None,
        },
        ood_evaluation={
            "status": "not_evaluated",
            "method": None,
            "threshold": None,
            "score_asset_sha256": None,
        },
        downstream_impact=_empty_downstream(),
        runtime=_empty_runtime(),
        processing_allowed=True,
        can_feed_decision_layer=False,
        reason_blocked=reason,
    )
    evaluation_sha256 = canonical_model_sha256(evaluation)
    product = _observation_product(
        context=context,
        event_id=event_id,
        run=run,
        run_sha256=run_sha256,
        evaluation_sha256=evaluation_sha256,
        product_id="fixture-sar-candidate-product-v2",
        generated_at=generated_at,
        source_name="FloodGuard deterministic candidate product fixture",
        dataset_mode="fixture_demo",
        git_commit=public_run.git_commit,
        valid_coverage_fraction=0.8,
        abstained_fraction=0.2,
        sensor_quality_status="passed",
        processing_allowed=True,
        reason=reason,
    )
    return _signed_bundle(
        context=context,
        event_id=event_id,
        run=run,
        evaluation=evaluation,
        product=product,
        registry_entry_id="fixture-sar-accepted-candidate-v1",
        registry_status="candidate",
        issued_at=generated_at,
        reason=reason,
    )


def _mae_sai_bundle(
    context: EvidenceContext,
    scoped_runs: list[ModelRun],
) -> RegistryProjectionBundle:
    if (
        context.study_area_id != MAE_SAI_STUDY_AREA
        or context.model_run_id is not None
        or scoped_runs
    ):
        raise ArtifactUnavailable("Mae Sai registry must remain unbound.")
    generated_at = context.generated_at
    event_id = MAE_SAI_EVENT_ID
    reason = (
        "Blocked: the Mae Sai package has no qualified in-area event-flood reference, "
        "executed controlled evaluation, or bound model run. This all-abstain technical "
        "projection is not observed flood evidence; its public signature is non-authoritative."
    )
    model_sha256 = _label_sha256(
        "unexecuted Mae Sai GeoAI candidate configuration v2"
    )
    run = ModelRunV2(
        dataset_mode="candidate",
        operational_status="non_operational",
        source_timestamp=_context_source_timestamp(context),
        generated_at=generated_at,
        confidence_class="low",
        source_name="Mae Sai unexecuted GeoAI candidate configuration",
        assumptions=[
            "This record describes a blocked experiment contract, not trained model weights.",
            "Its model_sha256 is a synthetic configuration identity, not a weights digest.",
            "The active Mae Sai evidence context deliberately remains unbound to this record.",
        ],
        data_version=context.data_version,
        git_commit="22fc172aca78937bb7d1f8675d08527a8517da68",
        run_id="mae-sai-geoai-evaluation-blocked-v2",
        study_area_id=context.study_area_id,
        event_id=event_id,
        evidence_kind="external_algorithmic_baseline",
        run_status="blocked",
        model={
            "model_id": "mae-sai-geoai-unet-challenger-v2",
            "model_revision": "unexecuted-contract",
            "model_family": "geoai_unet_fpn",
            "backend": "smp",
            "architecture": "unet",
            "encoder": "resnet34",
            "encoder_weights": None,
            "framework": "geoai",
            "framework_version": "blocked-unexecuted",
            "framework_commit": None,
            "model_sha256": model_sha256,
        },
        input_manifest_rows=[
            {
                "role": "candidate_source_bundle",
                "modality": "other_context",
                "product_id": "mae-sai-candidate-source-bundle-v1",
                "sha256": context.evidence_package_sha256,
                "source_timestamp": _context_source_timestamp(context),
                "processing_allowed": False,
            }
        ],
        feature_contract={
            "feature_schema_id": "geoai-eight-band-contract-v2",
            "value_domain": "encoded_uint8",
            "dtype": "uint8",
            "channel_count": 8,
            "channel_names": [
                "pre_vv",
                "post_vv",
                "pre_vh",
                "post_vh",
                "vv_change",
                "vh_change",
                "terrain",
                "permanent_water",
            ],
            "preprocessing_sidecar_sha256": _label_sha256(
                "Mae Sai blocked preprocessing contract v2"
            ),
            "feature_stack_sha256": _label_sha256(
                "Mae Sai unavailable feature stack projection v2"
            ),
        },
        target_contract={
            "class_schema_id": "temporary-flood-binary-v1",
            "classes": [
                {"index": 0, "name": "not_flooded", "training_role": "negative"},
                {"index": 1, "name": "temporary_flood", "training_role": "positive"},
                {"index": 255, "name": "unknown", "training_role": "ignore"},
            ],
            "reference_mask_status": "blocked",
            "label_release_sha256": None,
        },
        training_lineage={
            "input_manifest_sha256": context.evidence_package_sha256,
            "training_dataset_manifest_sha256": None,
            "label_release_sha256": None,
            "prepared_tile_manifest_sha256": None,
            "controlled_model_run_receipt_sha256": None,
            "threshold_selection_receipt_sha256": None,
            "calibration_receipt_sha256": None,
        },
        partition_contract={
            "partition_manifest_sha256": None,
            "training_partition_sha256": None,
            "calibration_partition_sha256": None,
            "final_holdout_partition_sha256": None,
            "train_ids": [],
            "calibration_ids": [],
            "final_holdout_ids": [],
        },
        inference_contract={
            "target_crs": "EPSG:4326",
            "resolution": [0.0001, 0.0001],
            "bounds": [99.75, 20.25, 100.15, 20.55],
            "tile_size": 256,
            "overlap": 64,
            "stride": 192,
            "batch_size": 1,
            "device": "unassigned",
            "probability_threshold": 0.5,
        },
        processing_allowed=False,
        can_feed_decision_layer=False,
        reason_blocked=reason,
    )
    run_sha256 = canonical_model_sha256(run)
    evaluation = ModelEvaluationV2(
        dataset_mode="candidate",
        operational_status="non_operational",
        source_timestamp=_context_source_timestamp(context),
        generated_at=generated_at,
        confidence_class="low",
        source_name="Mae Sai blocked controlled evaluation projection",
        assumptions=[
            "No controlled evaluation was executed.",
            "Null metrics are preserved and are not substituted from weak-label work.",
        ],
        data_version=context.data_version,
        git_commit=run.git_commit,
        evaluation_id="mae-sai-qualified-evaluation-blocked-v2",
        experiment_id="mae-sai-controlled-three-model-blocked-v2",
        study_area_id=context.study_area_id,
        event_ids=[event_id],
        model_run_id=run.run_id,
        model_id=run.model.model_id,
        model_sha256=run.model.model_sha256,
        model_run_manifest_sha256=run_sha256,
        controlled_result_receipt_sha256=None,
        evaluation_status="blocked",
        evaluation_scope="not_evaluated",
        reference_evidence={
            "reference_mask_status": "blocked",
            "reference_mask_sha256": None,
            "label_release_sha256": None,
            "reviewer_qualification_receipt_sha256": None,
        },
        partition_evidence={
            "partition_manifest_sha256": None,
            "training_partition_sha256": None,
            "calibration_partition_sha256": None,
            "final_holdout_partition_sha256": None,
        },
        threshold_evidence={
            "threshold": None,
            "threshold_selection_receipt_sha256": None,
            "selection_scope": "not_selected",
            "final_holdout_evaluated_during_selection": False,
        },
        overall_metrics=_empty_metrics(),
        event_metrics=[],
        error_strata=[],
        calibration={
            "status": "not_evaluated",
            "method": None,
            "reliability_asset_sha256": None,
        },
        selective_prediction={
            "status": "not_evaluated",
            "risk_coverage_asset_sha256": None,
        },
        ood_evaluation={
            "status": "not_evaluated",
            "method": None,
            "threshold": None,
            "score_asset_sha256": None,
        },
        downstream_impact=_empty_downstream(),
        runtime=_empty_runtime(),
        processing_allowed=False,
        can_feed_decision_layer=False,
        reason_blocked=reason,
    )
    evaluation_sha256 = canonical_model_sha256(evaluation)
    product = _observation_product(
        context=context,
        event_id=event_id,
        run=run,
        run_sha256=run_sha256,
        evaluation_sha256=evaluation_sha256,
        product_id="mae-sai-all-abstain-blocked-product-v2",
        generated_at=generated_at,
        source_name="Mae Sai all-abstain blocked product projection",
        dataset_mode="candidate",
        git_commit=run.git_commit,
        valid_coverage_fraction=0.0,
        abstained_fraction=1.0,
        sensor_quality_status="not_evaluated",
        processing_allowed=False,
        reason=reason,
    )
    return _signed_bundle(
        context=context,
        event_id=event_id,
        run=run,
        evaluation=evaluation,
        product=product,
        registry_entry_id="mae-sai-model-evaluation-blocked-v1",
        registry_status="blocked",
        issued_at=generated_at,
        reason=reason,
    )


def _observation_product(
    *,
    context: EvidenceContext,
    event_id: str,
    run: ModelRunV2,
    run_sha256: str,
    evaluation_sha256: str,
    product_id: str,
    generated_at: datetime,
    source_name: str,
    dataset_mode: str,
    git_commit: str,
    valid_coverage_fraction: float,
    abstained_fraction: float,
    sensor_quality_status: str,
    processing_allowed: bool,
    reason: str,
) -> FloodObservationProductV2:
    prefix = (
        f"offline-demo/mae-sai/model-evidence/{product_id}"
        if context.study_area_id == MAE_SAI_STUDY_AREA
        else f"model-registry/{context.study_area_id}/{product_id}"
    )
    asset_specs = [
        (
            "flood_probability",
            "float32",
            "flood_probability_0_1",
            -9999.0,
            0.0,
            1.0,
        ),
        ("validity_mask", "uint8", "validity", 255.0, 0.0, 1.0),
        ("sensor_quality_mask", "uint8", "sensor_quality", 255.0, 0.0, 4.0),
        ("model_uncertainty", "float32", "uncertainty", -9999.0, 0.0, 1.0),
        ("abstention_mask", "uint8", "abstention", 255.0, 0.0, 1.0),
    ]
    assets: list[dict[str, Any]] = []
    for role, dtype, band_name, nodata, minimum, maximum in asset_specs:
        relative_path = f"{prefix}/{role}.descriptor.json"
        descriptor = _observation_asset_descriptor(
            product_id=product_id,
            run_id=run.run_id,
            study_area_id=context.study_area_id,
            event_id=event_id,
            role=role,
            dtype=dtype,
            band_name=band_name,
            nodata=nodata,
            minimum=minimum,
            maximum=maximum,
            valid_coverage_fraction=valid_coverage_fraction,
            abstained_fraction=abstained_fraction,
            processing_allowed=processing_allowed,
            reason=reason,
        )
        assets.append(
            {
                "role": role,
                "relative_path": relative_path,
                "media_type": (
                    "application/vnd.floodguard.blocked-observation-"
                    "asset-descriptor+json"
                ),
                "sha256": hashlib.sha256(canonical_json(descriptor)).hexdigest(),
                "dtype": dtype,
                "band_name": band_name,
                "nodata": nodata,
                "minimum": minimum,
                "maximum": maximum,
            }
        )
    return FloodObservationProductV2(
        dataset_mode=dataset_mode,
        operational_status="non_operational",
        source_timestamp=_context_source_timestamp(context),
        generated_at=generated_at,
        confidence_class="low",
        source_name=source_name,
        assumptions=[
            (
                "Public deterministic projection only; asset digests address exact "
                "JSON descriptors and do not claim that rasters were materialized."
            ),
            "No-data and abstention remain unknown and are never filled as dry.",
        ],
        data_version=context.data_version,
        git_commit=git_commit,
        product_id=product_id,
        run_id=run.run_id,
        study_area_id=context.study_area_id,
        event_id=event_id,
        evidence_kind="external_algorithmic_baseline",
        source_manifest_sha256=context.evidence_package_sha256,
        model_run_manifest_sha256=run_sha256,
        model_sha256=run.model.model_sha256,
        evaluation_manifest_sha256=evaluation_sha256,
        grid={
            "crs": run.inference_contract.target_crs,
            "resolution": run.inference_contract.resolution,
            "bounds": run.inference_contract.bounds,
            "width": 3 if dataset_mode == "fixture_demo" else 4000,
            "height": 2 if dataset_mode == "fixture_demo" else 3000,
            "transform": [
                run.inference_contract.resolution[0],
                0.0,
                run.inference_contract.bounds[0],
                0.0,
                -run.inference_contract.resolution[1],
                run.inference_contract.bounds[3],
            ],
            "nodata": -9999.0,
            "grid_sha256": _label_sha256(f"{prefix}:grid"),
        },
        assets=assets,
        valid_coverage_fraction=valid_coverage_fraction,
        abstained_fraction=abstained_fraction,
        sensor_quality_status=sensor_quality_status,
        ood_status="not_evaluated",
        review_required_reasons=[reason],
        counts_as_observed_evidence=False,
        processing_allowed=processing_allowed,
        can_feed_decision_layer=False,
        reason_blocked=reason,
    )


def observation_asset_descriptors(
    product: FloodObservationProductV2,
) -> dict[str, dict[str, Any]]:
    """Reconstruct and verify exact non-raster descriptors named by a product."""

    descriptors: dict[str, dict[str, Any]] = {}
    for asset in product.assets:
        descriptor = _observation_asset_descriptor(
            product_id=product.product_id,
            run_id=product.run_id,
            study_area_id=product.study_area_id,
            event_id=product.event_id,
            role=asset.role,
            dtype=asset.dtype,
            band_name=asset.band_name,
            nodata=asset.nodata,
            minimum=asset.minimum,
            maximum=asset.maximum,
            valid_coverage_fraction=product.valid_coverage_fraction,
            abstained_fraction=product.abstained_fraction,
            processing_allowed=product.processing_allowed,
            reason=product.reason_blocked,
        )
        actual_sha256 = hashlib.sha256(canonical_json(descriptor)).hexdigest()
        if not hmac.compare_digest(actual_sha256, asset.sha256):
            raise ArtifactUnavailable(
                f"Observation asset descriptor hash mismatch for {asset.role}."
            )
        descriptors[asset.relative_path] = descriptor
    return descriptors


def _observation_asset_descriptor(
    *,
    product_id: str,
    run_id: str,
    study_area_id: str,
    event_id: str,
    role: str,
    dtype: str,
    band_name: str | None,
    nodata: float | None,
    minimum: float | None,
    maximum: float | None,
    valid_coverage_fraction: float,
    abstained_fraction: float,
    processing_allowed: bool,
    reason: str,
) -> dict[str, Any]:
    """Describe an intentionally unmaterialized band without claiming a raster."""

    return {
        "schema_version": "1.0",
        "descriptor_type": "floodguard.blocked_observation_asset",
        "product_id": product_id,
        "run_id": run_id,
        "study_area_id": study_area_id,
        "event_id": event_id,
        "role": role,
        "dtype": dtype,
        "band_name": band_name,
        "nodata": nodata,
        "minimum": minimum,
        "maximum": maximum,
        "materialization_status": "descriptor_only_no_raster",
        "valid_coverage_fraction": valid_coverage_fraction,
        "abstained_fraction": abstained_fraction,
        "counts_as_observed_evidence": False,
        "processing_allowed": processing_allowed,
        "can_feed_decision_layer": False,
        "reason_blocked": reason,
    }


def _signed_bundle(
    *,
    context: EvidenceContext,
    event_id: str,
    run: ModelRunV2,
    evaluation: ModelEvaluationV2,
    product: FloodObservationProductV2,
    registry_entry_id: str,
    registry_status: str,
    issued_at: datetime,
    reason: str,
) -> RegistryProjectionBundle:
    payload = ModelRegistryPayloadV1(
        registry_entry_id=registry_entry_id,
        study_area_id=context.study_area_id,
        event_id=event_id,
        evidence_kind="external_algorithmic_baseline",
        source_bundle_sha256=context.evidence_package_sha256,
        model_run_id=run.run_id,
        model_id=run.model.model_id,
        model_sha256=run.model.model_sha256,
        model_run_manifest_sha256=canonical_model_sha256(run),
        evaluation_id=evaluation.evaluation_id,
        evaluation_manifest_sha256=canonical_model_sha256(evaluation),
        controlled_result_receipt_sha256=(
            evaluation.controlled_result_receipt_sha256
        ),
        product_id=product.product_id,
        product_manifest_sha256=canonical_model_sha256(product),
        promotion_acceptance_receipt_sha256=None,
        field_validation_receipt_sha256=None,
        agency_acceptance_receipt_sha256=None,
        dataset_mode=context.dataset_mode.value,
        operational_status=context.operational_status.value,
        registry_status=registry_status,
        permitted_use="report_only",
        issued_at=issued_at,
        valid_from=issued_at,
        expires_at=issued_at + timedelta(days=3650),
        official_warning=False,
        can_feed_decision_layer=False,
        reason_blocked=reason,
    )
    payload_bytes = canonical_json(payload.model_dump(mode="json"))
    entry = SignedModelRegistryEntryV1(
        payload=payload,
        signature={
            "algorithm": "HMAC-SHA256",
            "key_id": PROJECTION_KEY_ID,
            "payload_sha256": hashlib.sha256(payload_bytes).hexdigest(),
            "value": hmac.new(
                PUBLIC_PROJECTION_TEST_KEY,
                payload_bytes,
                hashlib.sha256,
            ).hexdigest(),
        },
    )
    return RegistryProjectionBundle(
        model_run=run,
        evaluation=evaluation,
        product=product,
        entry=entry,
    )


def _empty_metrics() -> dict[str, None]:
    return {
        "sample_count": None,
        "true_positive": None,
        "false_positive": None,
        "false_negative": None,
        "true_negative": None,
        "iou": None,
        "f1_dice": None,
        "precision": None,
        "recall": None,
        "boundary_f1": None,
        "signed_area_error_ratio": None,
        "absolute_area_error_ratio": None,
        "brier_score": None,
        "negative_log_likelihood": None,
        "expected_calibration_error": None,
    }


def _empty_downstream() -> dict[str, Any]:
    return {
        "status": "not_evaluated",
        "population_absolute_error": None,
        "critical_road_false_negative_count": None,
        "access_classification_flip_count": None,
        "equity_gap_absolute_error": None,
        "fpps_mean_absolute_error": None,
        "fpps_rank_correlation": None,
        "action_class_flip_count": None,
        "artifact_sha256": None,
    }


def _empty_runtime() -> dict[str, Any]:
    return {
        "training_seconds": None,
        "calibration_seconds": None,
        "inference_seconds": None,
        "total_seconds": None,
        "peak_memory_mb": None,
        "device": None,
        "hardware_class": None,
    }


def _label_sha256(label: str) -> str:
    """Return a synthetic fixture/configuration identity, never a weights receipt."""

    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _context_source_timestamp(context: EvidenceContext) -> datetime:
    timestamps = [
        item.source_timestamp
        for item in context.source_components
        if item.source_timestamp is not None
    ]
    if not timestamps:
        raise ArtifactUnavailable("Evidence context has no source timestamp for registry use.")
    return max(timestamps)
