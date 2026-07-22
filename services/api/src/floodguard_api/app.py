"""FastAPI application exposing versioned FloodGuard artifacts."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Sequence
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.middleware.gzip import GZipMiddleware

from floodguard_api.dataset_registry import (
    MAE_SAI_STUDY_AREA,
    DatasetRegistry,
    LayerFilterError,
    filter_geojson_payload,
    parse_bbox,
    visible_layers_for_role,
)
from floodguard_api.models import (
    ActionClass,
    ApiError,
    AreaDecision,
    BriefResponse,
    ConfidenceClass,
    EvidenceContext,
    EvidenceRecord,
    HealthResponse,
    LayerCatalogItem,
    ModelRun,
    PublicPreparednessArea,
    ReadinessItem,
    ScenarioDefinition,
    ScenarioRunRequest,
    ScenarioRunResponse,
    StatusResponse,
    StudyArea,
)
from floodguard_api.pilot import PilotConfigurationError, PilotControl, PilotError
from floodguard_api.pilot_models import (
    AcceptanceReceiptRequest,
    AuditLogResponse,
    DeploymentMonitoringResponse,
    OperationalAssessmentRequest,
    OperationalAssessmentResponse,
    PilotCredential,
    PilotReadiness,
    PilotSessionResponse,
    ReceiptVerificationResponse,
    RetentionRequest,
    RetentionResponse,
    SignedAcceptanceReceipt,
)
from floodguard_api.repository import (
    ArtifactNotFound,
    ArtifactRepository,
    ArtifactUnavailable,
)
from floodguard_api.safety import PrivatePathError, assert_public_payload
from floodguard_api.scenario_registry import definitions, request_from_run_id

DEFAULT_CORS_ORIGINS = ("http://localhost:3000", "http://127.0.0.1:3000")


def create_app(
    repository: ArtifactRepository | DatasetRegistry | None = None,
    allowed_origins: Sequence[str] | None = None,
    pilot_control: PilotControl | None = None,
) -> FastAPI:
    """Build an injectable application for production and no-network tests."""

    artifact_repository = repository or DatasetRegistry()
    pilot = pilot_control or PilotControl.from_environment()
    application = FastAPI(
        title="FloodGuard Thailand artifact API",
        summary="Versioned decision-support artifacts for planning and judging.",
        description=(
            "Non-operational by default. This API is not an official warning system "
            "or live evacuation navigator."
        ),
        version="1.0.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    application.state.repository = artifact_repository
    application.state.pilot_control = pilot
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(allowed_origins or _configured_cors_origins()),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
    )
    application.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=6)

    @application.exception_handler(ArtifactNotFound)
    async def artifact_not_found(_: Request, exc: ArtifactNotFound) -> JSONResponse:
        error = ApiError(error="not_found", detail=str(exc))
        return JSONResponse(status_code=404, content=error.model_dump(mode="json"))

    @application.exception_handler(ArtifactUnavailable)
    async def artifact_unavailable(_: Request, exc: ArtifactUnavailable) -> JSONResponse:
        error = ApiError(
            error="artifact_unavailable",
            detail=str(exc),
            data_state="unavailable",
        )
        return JSONResponse(status_code=503, content=error.model_dump(mode="json"))

    @application.exception_handler(PrivatePathError)
    async def private_path_rejected(_: Request, exc: PrivatePathError) -> JSONResponse:
        error = ApiError(error="unsafe_response_rejected", detail=str(exc))
        return JSONResponse(status_code=500, content=error.model_dump(mode="json"))

    @application.exception_handler(LayerFilterError)
    async def invalid_layer_filter(_: Request, exc: LayerFilterError) -> JSONResponse:
        error = ApiError(error="invalid_layer_filter", detail=str(exc))
        return JSONResponse(status_code=422, content=error.model_dump(mode="json"))

    @application.exception_handler(PilotError)
    async def pilot_error(_: Request, exc: PilotError) -> JSONResponse:
        error = ApiError(error=exc.error_code, detail=str(exc))
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return JSONResponse(
            status_code=exc.status_code,
            content=error.model_dump(mode="json"),
            headers=headers,
        )

    def audit_protected_request(
        *,
        identity: PilotCredential | None,
        action: str,
        capability: str,
        outcome: Literal["allowed", "denied"],
        dataset_mode: str,
        reason: str,
        required: bool,
    ) -> None:
        """Append a redacted authorization outcome without persisting request input."""

        if not pilot.audit.configured:
            if required:
                raise PilotConfigurationError(
                    "Protected pilot operations require configured audit logging."
                )
            return
        now = pilot.now()
        audit_identity = identity or PilotCredential.model_construct(
            schema_version="1.0",
            subject="anonymous-request",
            roles=[],
            issued_at=now,
            expires_at=now,
            token_id="unverified-request",
            key_id="unverified-request",
        )
        pilot.audit.append(
            identity=audit_identity,
            action=action,
            outcome=outcome,
            details={
                "capability": capability,
                "dataset_mode": dataset_mode,
                "reason": reason,
            },
            now=now,
        )

    def require_capability(
        capability: str,
        action: str,
        *,
        official_input_only: bool = False,
    ) -> Any:
        def dependency(
            authorization: Annotated[str | None, Header()] = None,
        ) -> PilotCredential | None:
            dataset_mode = artifact_repository.status().dataset_mode.value
            if official_input_only and dataset_mode != "official_input":
                return None
            identity: PilotCredential | None = None
            try:
                identity = pilot.authenticate(authorization)
                pilot.require(identity, capability)
            except PilotError as exc:
                audit_protected_request(
                    identity=identity,
                    action=action,
                    capability=capability,
                    outcome="denied",
                    dataset_mode=dataset_mode,
                    reason=exc.error_code,
                    required=False,
                )
                raise
            audit_protected_request(
                identity=identity,
                action=action,
                capability=capability,
                outcome="allowed",
                dataset_mode=dataset_mode,
                reason="role_matrix",
                required=True,
            )
            return identity

        return dependency

    require_official_command_data = require_capability(
        "monitoring:read",
        "api:command-data:read",
        official_input_only=True,
    )
    require_official_scenario = require_capability(
        "assessment:run",
        "api:scenario:operate",
        official_input_only=True,
    )
    require_official_model = require_capability(
        "assessment:run",
        "api:model-evidence:read",
        official_input_only=True,
    )
    require_official_readiness = require_capability(
        "assessment:run",
        "api:data-readiness:read",
        official_input_only=True,
    )
    require_official_pilot_readiness = require_capability(
        "monitoring:read",
        "api:pilot-readiness:read",
        official_input_only=True,
    )
    require_session = require_capability("session:read", "api:pilot-session:read")
    require_monitoring = require_capability("monitoring:read", "api:pilot-monitoring:read")
    require_receipt_signing = require_capability("receipt:sign", "api:acceptance-receipt:sign")
    require_receipt_verification = require_capability(
        "receipt:verify", "api:acceptance-receipt:verify"
    )
    require_assessment = require_capability("assessment:run", "api:operational-assessment:run")
    require_audit_read = require_capability("audit:read", "api:audit-log:read")
    require_retention = require_capability("session:read", "api:retention:operate")

    @application.get(
        "/api/v1/health",
        response_model=HealthResponse,
        tags=["service"],
        summary="Report process health, not dataset freshness",
    )
    def health() -> HealthResponse:
        return HealthResponse(
            service_status="healthy",
            api_version="v1",
            service_name="floodguard-artifact-api",
        )

    @application.get(
        "/api/v1/status",
        response_model=StatusResponse,
        responses={503: {"model": ApiError}},
        tags=["data"],
    )
    def status(
        study_area: Literal["fixture_thailand_demo", "mae_sai_candidate_v1"] = (
            "fixture_thailand_demo"
        ),
    ) -> StatusResponse:
        if isinstance(artifact_repository, ArtifactRepository) and study_area == (
            "fixture_thailand_demo"
        ):
            result = artifact_repository.status()
        else:
            result = artifact_repository.status(study_area)
        return _public(result, pilot)

    @application.get(
        "/api/v1/study-areas",
        response_model=list[StudyArea],
        tags=["data"],
    )
    def study_areas() -> list[StudyArea]:
        return _public(artifact_repository.study_areas(), pilot)

    @application.get(
        "/api/v1/evidence-context",
        response_model=EvidenceContext,
        tags=["evidence"],
    )
    def evidence_context(
        study_area: Literal["fixture_thailand_demo", "mae_sai_candidate_v1"] = (
            "fixture_thailand_demo"
        ),
    ) -> EvidenceContext:
        if isinstance(artifact_repository, ArtifactRepository):
            artifact_repository._require_fixture_study_area(study_area)
            result = artifact_repository.evidence_context()
        else:
            result = artifact_repository.evidence_context(study_area)
        return _public(result, pilot)

    @application.get(
        "/api/v1/public-areas",
        response_model=list[PublicPreparednessArea],
        tags=["decisions"],
    )
    def public_areas(
        study_area: Literal["fixture_thailand_demo", "mae_sai_candidate_v1"] = (
            "fixture_thailand_demo"
        ),
    ) -> list[PublicPreparednessArea]:
        if isinstance(artifact_repository, ArtifactRepository):
            artifact_repository._require_fixture_study_area(study_area)
            result = artifact_repository.public_areas()
        else:
            result = artifact_repository.public_areas(study_area)
        return _public(result, pilot)

    @application.get(
        "/api/v1/evidence-records/{evidence_context_id}",
        response_model=EvidenceRecord,
        tags=["evidence"],
    )
    def evidence_record(evidence_context_id: str) -> EvidenceRecord:
        if isinstance(artifact_repository, ArtifactRepository):
            result = artifact_repository.evidence_record()
            if result.evidence_context.evidence_context_id != evidence_context_id:
                raise ArtifactNotFound(
                    f"Unknown evidence_context_id: {evidence_context_id}"
                )
        else:
            result = artifact_repository.evidence_record(evidence_context_id)
        return _public(result, pilot)

    @application.get(
        "/api/v1/areas",
        response_model=list[AreaDecision],
        response_model_exclude={"__all__": {"scenario_delta"}},
        responses={503: {"model": ApiError}},
        tags=["decisions"],
    )
    def areas(
        study_area: Literal["fixture_thailand_demo", "mae_sai_candidate_v1"] = (
            "fixture_thailand_demo"
        ),
        action_class: Annotated[list[ActionClass] | None, Query()] = None,
        confidence_class: Annotated[list[ConfidenceClass] | None, Query()] = None,
        min_fpps: Annotated[float, Query(ge=0, le=100)] = 0,
        _: PilotCredential | None = Depends(require_official_command_data),  # noqa: B008
    ) -> list[AreaDecision]:
        result = artifact_repository.areas(study_area)
        if action_class:
            allowed_actions = set(action_class)
            result = [area for area in result if area.action_class in allowed_actions]
        if confidence_class:
            allowed_confidence = set(confidence_class)
            result = [area for area in result if area.confidence_class in allowed_confidence]
        result = [area for area in result if area.fpps_0_100 >= min_fpps]
        return _public(result, pilot)

    @application.get(
        "/api/v1/areas/{area_id}",
        response_model=AreaDecision,
        response_model_exclude={"scenario_delta"},
        responses={404: {"model": ApiError}, 503: {"model": ApiError}},
        tags=["decisions"],
    )
    def area(
        area_id: str,
        study_area: Literal["fixture_thailand_demo", "mae_sai_candidate_v1"] = (
            "fixture_thailand_demo"
        ),
        _: PilotCredential | None = Depends(require_official_command_data),  # noqa: B008
    ) -> AreaDecision:
        return _public(artifact_repository.area(area_id, study_area), pilot)

    @application.get(
        "/api/v1/layers",
        response_model=list[LayerCatalogItem],
        tags=["data"],
    )
    def layers(
        study_area: Literal["fixture_thailand_demo", "mae_sai_candidate_v1"] = (
            "fixture_thailand_demo"
        ),
        role: Literal["public", "command", "studio"] = "command",
        _: PilotCredential | None = Depends(require_official_command_data),  # noqa: B008
    ) -> list[LayerCatalogItem]:
        if isinstance(artifact_repository, ArtifactRepository):
            result = visible_layers_for_role(
                artifact_repository.layers(study_area), role
            )
        else:
            result = artifact_repository.layers(study_area, role)
        return _public(result, pilot)

    @application.get(
        "/api/v1/layer-data/{layer_id}",
        response_class=JSONResponse,
        responses={404: {"model": ApiError}, 503: {"model": ApiError}},
        tags=["data"],
        include_in_schema=True,
    )
    def layer_data(
        layer_id: str,
        request: Request,
        study_area: Literal["fixture_thailand_demo", "mae_sai_candidate_v1"] = (
            "fixture_thailand_demo"
        ),
        area_id: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
        bbox: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
        facility_type: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
        verification_status: Annotated[
            Literal["open_context_candidate"] | None,
            Query(),
        ] = None,
        minimum_risk: Annotated[float, Query(ge=0, le=1)] = 0,
        detail: Literal["regional", "selected_area"] = "regional",
        role: Literal["public", "command", "studio"] = "command",
        _: PilotCredential | None = Depends(require_official_command_data),  # noqa: B008
    ) -> Response:
        if isinstance(artifact_repository, ArtifactRepository):
            visible_ids = {
                item.layer_id
                for item in visible_layers_for_role(
                    artifact_repository.layers(study_area), role
                )
            }
            if layer_id not in visible_ids:
                raise ArtifactNotFound(
                    f"Layer {layer_id} is not available for role {role} in {study_area}."
                )
            payload = artifact_repository.layer_data(layer_id, study_area)
        else:
            payload = artifact_repository.layer_data(layer_id, study_area, role)
        payload = filter_geojson_payload(
            payload,
            layer_id=layer_id,
            area_id=area_id,
            bbox=parse_bbox(bbox),
            facility_type=facility_type,
            verification_status=verification_status,
            minimum_risk=minimum_risk,
            detail=detail,
        )
        pilot.assert_operational_boundary(payload)
        assert_public_payload(payload)
        response = JSONResponse(
            content=payload,
            headers={
                "Cache-Control": "public, max-age=3600",
                "X-FloodGuard-Dataset-Mode": (
                    "candidate" if study_area == MAE_SAI_STUDY_AREA else "fixture_demo"
                ),
                "X-FloodGuard-Official-Warning": "false",
                "X-FloodGuard-Evidence-Context-Id": (
                    artifact_repository.evidence_context().evidence_context_id
                    if isinstance(artifact_repository, ArtifactRepository)
                    else artifact_repository.evidence_context(
                        study_area
                    ).evidence_context_id
                ),
                "X-FloodGuard-Artifact-SHA256": artifact_repository.layer_artifact_sha256(
                    layer_id,
                    study_area,
                ),
            },
        )
        content_sha256 = hashlib.sha256(response.body).hexdigest()
        etag = f'"sha256-{content_sha256}"'
        response.headers["ETag"] = etag
        response.headers["X-FloodGuard-Content-SHA256"] = content_sha256
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=dict(response.headers))
        return response

    @application.get(
        "/api/v1/briefs/{area_id}",
        response_model=BriefResponse,
        responses={404: {"model": ApiError}, 503: {"model": ApiError}},
        tags=["decisions"],
    )
    def brief(
        area_id: str,
        study_area: Literal["fixture_thailand_demo", "mae_sai_candidate_v1"] = (
            "fixture_thailand_demo"
        ),
        download: bool = False,
        _: PilotCredential | None = Depends(require_official_command_data),  # noqa: B008
    ) -> Any:
        result = artifact_repository.brief(area_id, study_area)
        pilot.assert_operational_boundary(result)
        assert_public_payload(result)
        if download:
            return Response(
                content=result.content_markdown,
                media_type="text/markdown; charset=utf-8",
                headers={
                    "Content-Disposition": f'attachment; filename="{result.file_name}"',
                    "X-FloodGuard-Official-Warning": "false",
                    "X-FloodGuard-Source-Timestamp": result.source_timestamp.isoformat(),
                },
            )
        return result

    @application.get(
        "/api/v1/scenarios",
        response_model=list[ScenarioDefinition],
        tags=["scenarios"],
    )
    def scenarios(
        study_area: Literal["fixture_thailand_demo", "mae_sai_candidate_v1"] = (
            "fixture_thailand_demo"
        ),
        _: PilotCredential | None = Depends(require_official_scenario),  # noqa: B008
    ) -> list[ScenarioDefinition]:
        if isinstance(artifact_repository, DatasetRegistry):
            result = artifact_repository.scenarios(study_area)
        else:
            artifact_repository._require_fixture_study_area(study_area)
            result = definitions()
        return _public(result, pilot)

    @application.post(
        "/api/v1/scenario-runs",
        response_model=ScenarioRunResponse,
        status_code=201,
        responses={503: {"model": ApiError}},
        tags=["scenarios"],
    )
    def scenario_run(
        request: ScenarioRunRequest,
        _: PilotCredential | None = Depends(require_official_scenario),  # noqa: B008
    ) -> ScenarioRunResponse:
        return _public(artifact_repository.run_scenario(request), pilot)

    @application.get(
        "/api/v1/scenario-runs/{run_id}",
        response_model=ScenarioRunResponse,
        responses={404: {"model": ApiError}, 503: {"model": ApiError}},
        tags=["scenarios"],
    )
    def scenario_run_result(
        run_id: str,
        _: PilotCredential | None = Depends(require_official_scenario),  # noqa: B008
    ) -> ScenarioRunResponse:
        request = request_from_run_id(run_id)
        if request is None:
            raise ArtifactNotFound(f"Unknown scenario run_id: {run_id}")
        return _public(artifact_repository.run_scenario(request), pilot)

    @application.get(
        "/api/v1/model-runs",
        response_model=list[ModelRun],
        responses={503: {"model": ApiError}},
        tags=["models"],
    )
    def model_runs(
        _: PilotCredential | None = Depends(require_official_model),  # noqa: B008
    ) -> list[ModelRun]:
        return _public(artifact_repository.model_runs(), pilot)

    @application.get(
        "/api/v1/model-runs/{run_id}",
        response_model=ModelRun,
        responses={404: {"model": ApiError}, 503: {"model": ApiError}},
        tags=["models"],
    )
    def model_run(
        run_id: str,
        _: PilotCredential | None = Depends(require_official_model),  # noqa: B008
    ) -> ModelRun:
        return _public(artifact_repository.model_run(run_id), pilot)

    @application.get(
        "/api/v1/data-readiness",
        response_model=list[ReadinessItem],
        tags=["models"],
    )
    def data_readiness(
        _: PilotCredential | None = Depends(require_official_readiness),  # noqa: B008
    ) -> list[ReadinessItem]:
        return _public(artifact_repository.readiness(), pilot)

    @application.get(
        "/api/v1/pilot/readiness",
        response_model=PilotReadiness,
        tags=["agency-pilot"],
        summary="Expose sanitized pilot readiness without granting operational status",
    )
    def pilot_readiness(
        _: PilotCredential | None = Depends(require_official_pilot_readiness),  # noqa: B008
    ) -> PilotReadiness:
        current = artifact_repository.status()
        return pilot.readiness(
            dataset_mode=current.dataset_mode.value,
            study_area=current.study_area,
            data_version=current.data_version,
            served_payload=current,
        )

    @application.get(
        "/api/v1/pilot/session",
        response_model=PilotSessionResponse,
        tags=["agency-pilot"],
    )
    def pilot_session(
        identity: PilotCredential = Depends(require_session),  # noqa: B008
    ) -> PilotSessionResponse:
        return pilot.session(identity)

    @application.get(
        "/api/v1/pilot/monitoring",
        response_model=DeploymentMonitoringResponse,
        tags=["agency-pilot"],
    )
    def pilot_monitoring(
        _: PilotCredential = Depends(require_monitoring),  # noqa: B008
    ) -> DeploymentMonitoringResponse:
        current = artifact_repository.status()
        return pilot.monitoring(
            dataset_mode=current.dataset_mode.value,
            study_area=current.study_area,
            data_version=current.data_version,
            data_state=current.data_state.value,
            source_timestamp=current.source_timestamp,
            served_payload=current,
        )

    @application.post(
        "/api/v1/pilot/acceptance-receipts",
        response_model=SignedAcceptanceReceipt,
        status_code=201,
        tags=["agency-pilot"],
    )
    def sign_acceptance_receipt(
        request: AcceptanceReceiptRequest,
        identity: PilotCredential = Depends(require_receipt_signing),  # noqa: B008
    ) -> SignedAcceptanceReceipt:
        return pilot.sign_acceptance(request, identity)

    @application.post(
        "/api/v1/pilot/acceptance-receipts/verify",
        response_model=ReceiptVerificationResponse,
        tags=["agency-pilot"],
    )
    def verify_acceptance_receipt(
        receipt: SignedAcceptanceReceipt,
        _: PilotCredential = Depends(require_receipt_verification),  # noqa: B008
    ) -> ReceiptVerificationResponse:
        return pilot.verify_receipt(receipt)

    @application.post(
        "/api/v1/pilot/operational-assessments",
        response_model=OperationalAssessmentResponse,
        tags=["agency-pilot"],
    )
    def operational_assessment(
        request: OperationalAssessmentRequest,
        _: PilotCredential = Depends(require_assessment),  # noqa: B008
    ) -> OperationalAssessmentResponse:
        return pilot.assess(request)

    @application.get(
        "/api/v1/pilot/audit-log",
        response_model=AuditLogResponse,
        tags=["agency-pilot"],
    )
    def pilot_audit_log(
        _: PilotCredential = Depends(require_audit_read),  # noqa: B008
    ) -> AuditLogResponse:
        return pilot.audit.read()

    @application.post(
        "/api/v1/pilot/retention",
        response_model=RetentionResponse,
        tags=["agency-pilot"],
    )
    def pilot_retention(
        request: RetentionRequest,
        identity: PilotCredential = Depends(require_retention),  # noqa: B008
    ) -> RetentionResponse:
        return pilot.run_retention(request, identity)

    return application


def _configured_cors_origins() -> tuple[str, ...]:
    configured = os.getenv("FLOODGUARD_CORS_ORIGINS", "")
    origins = (
        tuple(
            dict.fromkeys(
                origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()
            )
        )
        or DEFAULT_CORS_ORIGINS
    )
    for origin in origins:
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("FLOODGUARD_CORS_ORIGINS must contain comma-separated HTTP(S) origins")
    return origins


def _public(value: Any, pilot: PilotControl) -> Any:
    pilot.assert_operational_boundary(value)
    assert_public_payload(value)
    return value


app = create_app()
