"""FastAPI application exposing versioned FloodGuard artifacts."""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from floodguard_api.models import (
    ActionClass,
    ApiError,
    AreaDecision,
    BriefResponse,
    ConfidenceClass,
    HealthResponse,
    LayerCatalogItem,
    ModelRun,
    ReadinessItem,
    ScenarioDefinition,
    ScenarioRunRequest,
    ScenarioRunResponse,
    StatusResponse,
    StudyArea,
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
    repository: ArtifactRepository | None = None,
    allowed_origins: Sequence[str] | None = None,
) -> FastAPI:
    """Build an injectable application for production and no-network tests."""

    artifact_repository = repository or ArtifactRepository()
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
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(allowed_origins or _configured_cors_origins()),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

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
    def status() -> StatusResponse:
        return _public(artifact_repository.status())

    @application.get(
        "/api/v1/study-areas",
        response_model=list[StudyArea],
        tags=["data"],
    )
    def study_areas() -> list[StudyArea]:
        return _public(artifact_repository.study_areas())

    @application.get(
        "/api/v1/areas",
        response_model=list[AreaDecision],
        response_model_exclude={"__all__": {"scenario_delta"}},
        responses={503: {"model": ApiError}},
        tags=["decisions"],
    )
    def areas(
        study_area: Literal["fixture_thailand_demo"] = "fixture_thailand_demo",
        action_class: Annotated[list[ActionClass] | None, Query()] = None,
        confidence_class: Annotated[list[ConfidenceClass] | None, Query()] = None,
        min_fpps: Annotated[float, Query(ge=0, le=100)] = 0,
    ) -> list[AreaDecision]:
        del study_area
        result = artifact_repository.areas()
        if action_class:
            allowed_actions = set(action_class)
            result = [area for area in result if area.action_class in allowed_actions]
        if confidence_class:
            allowed_confidence = set(confidence_class)
            result = [area for area in result if area.confidence_class in allowed_confidence]
        result = [area for area in result if area.fpps_0_100 >= min_fpps]
        return _public(result)

    @application.get(
        "/api/v1/areas/{area_id}",
        response_model=AreaDecision,
        response_model_exclude={"scenario_delta"},
        responses={404: {"model": ApiError}, 503: {"model": ApiError}},
        tags=["decisions"],
    )
    def area(area_id: str) -> AreaDecision:
        return _public(artifact_repository.area(area_id))

    @application.get(
        "/api/v1/layers",
        response_model=list[LayerCatalogItem],
        tags=["data"],
    )
    def layers() -> list[LayerCatalogItem]:
        return _public(artifact_repository.layers())

    @application.get(
        "/api/v1/layer-data/{layer_id}",
        response_class=JSONResponse,
        responses={404: {"model": ApiError}, 503: {"model": ApiError}},
        tags=["data"],
        include_in_schema=True,
    )
    def layer_data(layer_id: str) -> JSONResponse:
        payload = artifact_repository.layer_data(layer_id)
        assert_public_payload(payload)
        return JSONResponse(
            content=payload,
            headers={
                "Cache-Control": "public, max-age=300",
                "X-FloodGuard-Dataset-Mode": "fixture_demo",
                "X-FloodGuard-Official-Warning": "false",
            },
        )

    @application.get(
        "/api/v1/briefs/{area_id}",
        response_model=BriefResponse,
        responses={404: {"model": ApiError}, 503: {"model": ApiError}},
        tags=["decisions"],
    )
    def brief(area_id: str, download: bool = False) -> Any:
        result = artifact_repository.brief(area_id)
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
    def scenarios() -> list[ScenarioDefinition]:
        return _public(definitions())

    @application.post(
        "/api/v1/scenario-runs",
        response_model=ScenarioRunResponse,
        status_code=201,
        responses={503: {"model": ApiError}},
        tags=["scenarios"],
    )
    def scenario_run(request: ScenarioRunRequest) -> ScenarioRunResponse:
        return _public(artifact_repository.run_scenario(request))

    @application.get(
        "/api/v1/scenario-runs/{run_id}",
        response_model=ScenarioRunResponse,
        responses={404: {"model": ApiError}, 503: {"model": ApiError}},
        tags=["scenarios"],
    )
    def scenario_run_result(run_id: str) -> ScenarioRunResponse:
        request = request_from_run_id(run_id)
        if request is None:
            raise ArtifactNotFound(f"Unknown scenario run_id: {run_id}")
        return _public(artifact_repository.run_scenario(request))

    @application.get(
        "/api/v1/model-runs",
        response_model=list[ModelRun],
        responses={503: {"model": ApiError}},
        tags=["models"],
    )
    def model_runs() -> list[ModelRun]:
        return _public(artifact_repository.model_runs())

    @application.get(
        "/api/v1/model-runs/{run_id}",
        response_model=ModelRun,
        responses={404: {"model": ApiError}, 503: {"model": ApiError}},
        tags=["models"],
    )
    def model_run(run_id: str) -> ModelRun:
        return _public(artifact_repository.model_run(run_id))

    @application.get(
        "/api/v1/data-readiness",
        response_model=list[ReadinessItem],
        tags=["models"],
    )
    def data_readiness() -> list[ReadinessItem]:
        return _public(artifact_repository.readiness())

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


def _public(value: Any) -> Any:
    assert_public_payload(value)
    return value


app = create_app()
