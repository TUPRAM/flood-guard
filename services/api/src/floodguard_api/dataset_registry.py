"""Fail-closed registry for immutable FloodGuard study-area bundles."""

from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal

import pandas as pd
from floodguard.access import calculate_access_loss
from floodguard.equity import compute_equity_gap, equity_input_from_access_loss
from floodguard.scenarios import run_access_scenario
from floodguard.scoring import assign_action_reason_code
from pydantic import BaseModel, ConfigDict, Field, model_validator

from floodguard_api.config import RepositoryPaths
from floodguard_api.models import (
    AreaDecision,
    BriefResponse,
    EvidenceContext,
    EvidenceRecord,
    EvidenceState,
    FacilityEvidence,
    LayerCatalogItem,
    ModelRun,
    PublicPreparednessArea,
    ReadinessItem,
    RoadEvidence,
    ScenarioAreaResult,
    ScenarioDefinition,
    ScenarioOverallResult,
    ScenarioRunRequest,
    ScenarioRunResponse,
    SourceComponent,
    StatusResponse,
    StudyArea,
)
from floodguard_api.repository import (
    ArtifactNotFound,
    ArtifactRepository,
    ArtifactUnavailable,
)
from floodguard_api.scenario_registry import (
    ACCESS_METHOD,
    MAE_SAI_BACKEND_CONFIG_VERSION,
    MAE_SAI_CLOSE_EDGE_ID,
    MAE_SAI_TEMPORARY_SHELTER_NODE,
    definitions,
    run_id_for,
)

FIXTURE_STUDY_AREA = "fixture_thailand_demo"
MAE_SAI_STUDY_AREA = "mae_sai_candidate_v1"
MAE_SAI_DATA_VERSION = "mae-sai-candidate-2024-09-15-v1"
MAE_SAI_DATA_GIT_COMMIT = "22fc172aca78937bb7d1f8675d08527a8517da68"
MAE_SAI_SOURCE_TIMESTAMP = datetime(2024, 9, 15, 23, 16, 1, tzinfo=UTC)
MAE_SAI_EVIDENCE_CONTEXT_ID = (
    "mae-sai:2024-09:mae-sai-candidate-2024-09-15-v1"
)
MAE_SAI_EVIDENCE_PACKAGE_ID = "mae-sai-historic-planning-2024-09-v1"
MAE_SAI_MANIFEST_RELATIVE_PATH = (
    "services/api/data/study_area_bundles/mae_sai_candidate_v1.json"
)
# This digest is filled from the reviewed manifest and deliberately lives outside it.
MAE_SAI_MANIFEST_SHA256 = "0bb7feff4b84d7a202b006856352d619d66607155bdf41430d5a5ea0f9d52026"
MAE_SAI_PUBLIC_PROJECTION_RELATIVE_PATH = (
    "apps/web/public/offline-demo/mae-sai/public-areas.json"
)
# Updated only after the deterministic browser projection has been regenerated and reviewed.
MAE_SAI_PUBLIC_PROJECTION_SHA256 = (
    "6e60cb3e505c5dde309005b41b547b6126623537b34a8e2d44b4e856852707de"
)
MAE_SAI_SCENARIO_MANIFEST_RELATIVE_PATH = "outputs/mae_sai_scenario_inputs_manifest.json"
MAE_SAI_SCENARIO_MANIFEST_SHA256 = (
    "20ce7a6d7007daeccbb64afcbabc00e447bb96de8c66eb44776a827be6c61a04"
)


class _ManifestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)


class BundleLayerSpec(_ManifestModel):
    """Immutable identity and safety contract for one committed GeoJSON layer."""

    layer_id: Literal[
        "administrative_boundaries",
        "priority_areas",
        "road_risk",
        "facilities",
        "access_hotspots",
    ]
    semantic_role: str = Field(min_length=1)
    role_visibility: tuple[Literal["public", "command", "studio"], ...] = Field(
        min_length=1
    )
    evidence_state: EvidenceState
    source_component_ids: tuple[str, ...] = Field(min_length=1)
    relative_path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    git_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    expected_feature_count: int = Field(ge=1)
    geometry_types: tuple[str, ...] = Field(min_length=1)
    join_key: Literal["subdistrict_id"]
    required_properties: tuple[str, ...] = Field(min_length=1)
    source_name: str = Field(min_length=1)
    source_timestamp: datetime
    source_license: str = Field(min_length=1)
    attribution: tuple[str, ...] = Field(min_length=1)
    confidence_class: Literal["low", "medium", "high"]
    processing_allowed: bool
    can_feed_decision_layer: bool
    reason_blocked: str = Field(min_length=1)

    @model_validator(mode="after")
    def preserve_relative_and_blocked_identity(self) -> BundleLayerSpec:
        relative = PurePosixPath(self.relative_path)
        if relative.is_absolute() or ".." in relative.parts or "\\" in self.relative_path:
            raise ValueError("bundle layer paths must be repository-relative POSIX paths")
        if self.can_feed_decision_layer:
            raise ValueError("the Mae Sai candidate bundle cannot feed the decision layer")
        if len(set(self.required_properties)) != len(self.required_properties):
            raise ValueError("required_properties must be unique")
        return self


class StudyAreaBundleManifest(_ManifestModel):
    """Validated manifest binding one study area to exact committed artifacts."""

    schema_version: Literal["1.0"]
    study_area_id: Literal["mae_sai_candidate_v1"]
    dataset_mode: Literal["candidate"]
    operational_status: Literal["non_operational"]
    official_warning: Literal[False]
    data_version: str = Field(min_length=1)
    git_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_timestamp: datetime
    generated_at: datetime
    evidence_context_id: str = Field(
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$"
    )
    evidence_package_id: str = Field(min_length=1)
    expected_crs: Literal["EPSG:4326"]
    expected_bounds: tuple[float, float, float, float]
    expected_area_ids: tuple[str, ...] = Field(min_length=1)
    assumptions: tuple[str, ...] = Field(min_length=1)
    source_components: tuple[SourceComponent, ...] = Field(min_length=1)
    layers: tuple[BundleLayerSpec, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def preserve_bundle_identity(self) -> StudyAreaBundleManifest:
        if self.data_version != MAE_SAI_DATA_VERSION:
            raise ValueError("Mae Sai data_version does not match the pinned registry identity")
        if self.git_commit != MAE_SAI_DATA_GIT_COMMIT:
            raise ValueError("Mae Sai git_commit does not match the pinned registry identity")
        if self.evidence_context_id != MAE_SAI_EVIDENCE_CONTEXT_ID:
            raise ValueError("Mae Sai evidence_context_id does not match the registry identity")
        if self.evidence_package_id != MAE_SAI_EVIDENCE_PACKAGE_ID:
            raise ValueError("Mae Sai evidence_package_id does not match the registry identity")
        min_x, min_y, max_x, max_y = self.expected_bounds
        if max_x <= min_x or max_y <= min_y:
            raise ValueError("expected_bounds must have positive area")
        if not (-180 <= min_x < max_x <= 180 and -90 <= min_y < max_y <= 90):
            raise ValueError("expected_bounds must be valid WGS84 coordinates")
        if len(set(self.expected_area_ids)) != len(self.expected_area_ids):
            raise ValueError("expected_area_ids must be unique")
        component_ids = {
            component.source_component_id for component in self.source_components
        }
        if len(component_ids) != len(self.source_components):
            raise ValueError("source component IDs must be unique")
        layer_ids = [layer.layer_id for layer in self.layers]
        if len(set(layer_ids)) != len(layer_ids):
            raise ValueError("layer IDs must be unique")
        if set(layer_ids) != {
            "administrative_boundaries",
            "priority_areas",
            "road_risk",
            "facilities",
            "access_hotspots",
        }:
            raise ValueError("Mae Sai bundle must contain the complete contracted layer set")
        for layer in self.layers:
            if not set(layer.source_component_ids).issubset(component_ids):
                raise ValueError("layer references an unknown source component")
            if "public" in layer.role_visibility:
                raise ValueError(
                    "source layers remain staff-only; public access uses a redacted projection"
                )
        return self


class ScenarioInputArtifact(_ManifestModel):
    role: Literal["population_nodes", "access_edges", "facility_candidates"]
    relative_path: Literal[
        "mae_sai_population_nodes.csv",
        "mae_sai_access_edges.csv",
        "mae_sai_facility_context.csv",
    ]
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    row_count: int = Field(ge=1)
    columns: tuple[str, ...] = Field(min_length=1)


class ScenarioInputManifest(_ManifestModel):
    schema_version: Literal["1.0"]
    study_area_id: Literal["mae_sai_candidate_v1"]
    dataset_mode: Literal["candidate"]
    operational_status: Literal["non_operational"]
    official_warning: Literal[False]
    data_version: str = Field(min_length=1)
    git_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_timestamp: datetime
    generated_at: datetime
    confidence_class: Literal["low"]
    source_name: str = Field(min_length=1)
    source_licenses: tuple[str, ...] = Field(min_length=1)
    processing_allowed: Literal[True]
    can_feed_decision_layer: Literal[False]
    reason_blocked: str = Field(min_length=1)
    processing_scope: Literal["mae_sai_candidate_access_scenario_inputs"]
    artifacts: tuple[ScenarioInputArtifact, ...] = Field(min_length=3, max_length=3)
    assumptions: tuple[str, ...] = Field(min_length=1)
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def preserve_scenario_inputs(self) -> ScenarioInputManifest:
        if self.data_version != MAE_SAI_DATA_VERSION:
            raise ValueError("scenario data_version does not match the pinned registry identity")
        if self.git_commit != MAE_SAI_DATA_GIT_COMMIT:
            raise ValueError("scenario git_commit does not match the pinned registry identity")
        if self.generated_at < self.source_timestamp:
            raise ValueError("scenario generated_at cannot predate source_timestamp")
        roles = [artifact.role for artifact in self.artifacts]
        if set(roles) != {"population_nodes", "access_edges", "facility_candidates"}:
            raise ValueError("scenario input roles are incomplete")
        if len(roles) != len(set(roles)):
            raise ValueError("scenario input roles must be unique")
        return self


class LayerFilterError(ValueError):
    """Raised when a layer filter is incompatible or malformed."""


class MaeSaiCandidateAdapter:
    """Serve the historic real-coordinate Mae Sai candidate without promotion."""

    def __init__(self, paths: RepositoryPaths | None = None) -> None:
        self.paths = paths or RepositoryPaths.discover()
        self.generated_at = datetime.now(UTC)
        self._scenario_cache: dict[str, ScenarioRunResponse] = {}
        self._baseline_cache: tuple[pd.DataFrame, pd.DataFrame] | None = None

    @property
    def manifest_path(self) -> Path:
        return self.paths.root / Path(MAE_SAI_MANIFEST_RELATIVE_PATH)

    @property
    def public_projection_path(self) -> Path:
        return self.paths.root / Path(MAE_SAI_PUBLIC_PROJECTION_RELATIVE_PATH)

    def status(self) -> StatusResponse:
        try:
            self._manifest()
            self._validated_public_projection()
        except ArtifactUnavailable as exc:
            state = "unavailable"
            confidence = "low"
            assumptions = [
                "The Mae Sai candidate bundle failed immutable validation.",
                str(exc),
            ]
            message_en = "Mae Sai candidate artifacts are unavailable; no fallback was substituted."
            message_th = "ชุดข้อมูลผู้สมัครแม่สายไม่พร้อมใช้งาน และไม่มีการแทนที่ด้วยข้อมูลชุดอื่น"
        else:
            state = "stale"
            confidence = "low"
            assumptions = list(self._manifest().assumptions)
            message_en = (
                "Historic Mae Sai candidate planning context; non-operational and not "
                "an official warning."
            )
            message_th = (
                "บริบทผู้สมัครแม่สายจากเหตุการณ์ในอดีต ใช้เพื่อการวางแผนเท่านั้น "
                "ไม่ใช่ระบบปฏิบัติการหรือประกาศเตือนภัยอย่างเป็นทางการ"
            )
        return StatusResponse(
            **self._common(
                source_name="FloodGuard immutable Mae Sai candidate bundle",
                assumptions=assumptions,
                confidence_class=confidence,
            ),
            evidence_context_id=MAE_SAI_EVIDENCE_CONTEXT_ID,
            evidence_package_id=MAE_SAI_EVIDENCE_PACKAGE_ID,
            study_area=MAE_SAI_STUDY_AREA,
            data_state=state,
            message_th=message_th,
            message_en=message_en,
        )

    def study_area(self) -> StudyArea:
        status = self.status()
        area_count = 8 if status.data_state.value != "unavailable" else 0
        return StudyArea(
            **self._common(
                source_name="HDX Thailand COD-AB and FloodGuard candidate analysis",
                assumptions=list(status.assumptions),
                confidence_class="low" if area_count else "low",
            ),
            study_area_id=MAE_SAI_STUDY_AREA,
            title_th="พื้นที่ศึกษาผู้สมัครแม่สาย จังหวัดเชียงราย",
            title_en="Mae Sai, Chiang Rai — historic candidate context",
            area_count=area_count,
            data_state=status.data_state,
        )

    def areas(self) -> list[AreaDecision]:
        layers = self._validated_layers()
        priorities = layers["priority_areas"]["features"]
        roads = layers["road_risk"]["features"]
        facilities = layers["facilities"]["features"]

        road_counts: dict[str, int] = {}
        bridge_counts: dict[str, int] = {}
        for feature in roads:
            properties = feature["properties"]
            area_id = str(properties["subdistrict_id"])
            road_counts[area_id] = road_counts.get(area_id, 0) + 1
            if properties["bridge_flag"] is True:
                bridge_counts[area_id] = bridge_counts.get(area_id, 0) + 1

        facility_counts: dict[str, int] = {}
        for feature in facilities:
            area_id = str(feature["properties"]["subdistrict_id"])
            facility_counts[area_id] = facility_counts.get(area_id, 0) + 1

        result: list[AreaDecision] = []
        for feature in priorities:
            row = feature["properties"]
            area_id = str(row["subdistrict_id"])
            assumptions = _unique_strings(
                [
                    row["assumptions"],
                    "Access is nearest-facility shortest-path threshold analysis, not 2SFCA.",
                    "Road values are modelled candidates, not observed closures.",
                    (
                        "Facilities are unverified open-context candidates, not designated "
                        "evacuation shelters."
                    ),
                ]
            )
            result.append(
                AreaDecision(
                    **self._common(
                        source_name=str(row["source_name"]),
                        assumptions=assumptions,
                        confidence_class="low",
                        source_timestamp=_parse_datetime(row["source_timestamp"]),
                    ),
                    evidence_context_id=MAE_SAI_EVIDENCE_CONTEXT_ID,
                    area_id=area_id,
                    area_name_th=_required_text(row.get("subdistrict_name_th"), area_id),
                    area_name_en=_required_text(row.get("subdistrict_name"), area_id),
                    fpps_0_100=float(row["fpps_0_100"]),
                    action_class=str(row["action_class"]),
                    action_reason_code=assign_action_reason_code(row),
                    top_reason=_required_text(row.get("top_reason"), "Candidate evidence only."),
                    flood_likelihood_0_100=float(row["flood_likelihood_0_100"]),
                    exposure_0_100=float(row["exposure_0_100"]),
                    access_gap_0_100=float(row["access_gap_0_100"]),
                    road_criticality_0_100=float(row["road_criticality_0_100"]),
                    vulnerability_context_0_100=float(row["vulnerability_context_0_100"]),
                    people_losing_30_min_access=int(
                        round(float(row["people_losing_30_min_access"]))
                    ),
                    equity_gap_ratio=_optional_number(row.get("equity_gap_ratio")),
                    road_evidence=RoadEvidence(
                        at_risk_segments=road_counts.get(area_id, 0),
                        bridge_count=bridge_counts.get(area_id, 0),
                        summary=(
                            "Modelled candidate road-risk evidence derived from ADM3 context; "
                            "field verification is required."
                        ),
                    ),
                    facility_evidence=FacilityEvidence(
                        facility_count=facility_counts.get(area_id, 0),
                        summary=(
                            "OpenStreetMap facility candidates; emergency role, operation, "
                            "capacity, and accessibility are unverified."
                        ),
                    ),
                )
            )
        return sorted(result, key=lambda item: item.area_id)

    def area(self, area_id: str) -> AreaDecision:
        for item in self.areas():
            if item.area_id == area_id:
                return item
        raise ArtifactNotFound(f"Unknown area_id for {MAE_SAI_STUDY_AREA}: {area_id}")

    def evidence_context(self) -> EvidenceContext:
        """Return the immutable Mae Sai package identity with no model substitution."""

        manifest = self._manifest()
        return EvidenceContext(
            evidence_context_id=manifest.evidence_context_id,
            study_area_id=manifest.study_area_id,
            data_version=manifest.data_version,
            evidence_package_id=manifest.evidence_package_id,
            evidence_package_sha256=MAE_SAI_MANIFEST_SHA256,
            model_run_id=None,
            dataset_mode=manifest.dataset_mode,
            operational_status=manifest.operational_status,
            official_warning=manifest.official_warning,
            generated_at=manifest.generated_at,
            source_components=list(manifest.source_components),
        )

    def public_areas(self) -> list[PublicPreparednessArea]:
        """Return reduced public records without A-E or score-component details."""

        return [
            PublicPreparednessArea.model_validate(feature["properties"])
            for feature in self._validated_public_projection()["features"]
        ]

    def evidence_record(self) -> EvidenceRecord:
        """Return the package-level audit record; qualified evaluation is absent."""

        context = self.evidence_context()
        return EvidenceRecord(
            evidence_record_id=f"{context.evidence_context_id}:blocked",
            evidence_context=context,
            evidence_scope="Historic Mae Sai planning candidate; no qualified evaluation",
            model_id=None,
            model_version=None,
            model_sha256=None,
            evaluation_sha256=None,
            decision="blocked",
            decision_authority=None,
            decision_at=None,
            operational_authorized=False,
            blockers=[
                "No qualified Thailand event-flood reference evaluation is published.",
                "Facility roles and current operation are not agency verified.",
                "Road evidence is area-summary context, not segment-raster intersection.",
                "No agency operational acceptance is recorded.",
            ],
            generated_at=context.generated_at,
        )

    def layers(
        self,
        role: Literal["public", "command", "studio"] | None = None,
    ) -> list[LayerCatalogItem]:
        manifest = self._manifest()
        selected_specs = [
            spec
            for spec in manifest.layers
            if role is None or role in spec.role_visibility
        ]
        staff_errors: dict[str, str] = {}
        for spec in selected_specs:
            try:
                self._validated_layer(manifest, spec)
            except ArtifactUnavailable as exc:
                staff_errors[spec.layer_id] = str(exc)
        public_error = ""
        if role in {None, "public"}:
            try:
                self._validated_public_projection()
            except ArtifactUnavailable as exc:
                public_error = str(exc)

        titles = {
            "administrative_boundaries": ("ขอบเขตพื้นที่รายงาน", "Reporting boundaries"),
            "priority_areas": ("พื้นที่จัดลำดับความสำคัญผู้สมัคร", "Candidate priority areas"),
            "road_risk": ("ความเสี่ยงถนนแบบจำลอง", "Modelled road-risk candidates"),
            "facilities": ("สถานที่ผู้สมัครที่ยังไม่ยืนยัน", "Unverified facility candidates"),
            "access_hotspots": ("จุดสูญเสียการเข้าถึงแบบจำลอง", "Modelled access hotspots"),
        }
        result: list[LayerCatalogItem] = []
        for spec in selected_specs:
            title_th, title_en = titles[spec.layer_id]
            bundle_error = staff_errors.get(spec.layer_id, "")
            assumptions = [
                spec.reason_blocked,
                "Historic candidate layer; not an official warning or live condition.",
            ]
            if bundle_error:
                assumptions.append(bundle_error)
            result.append(
                LayerCatalogItem(
                    **self._common(
                        source_name=spec.source_name,
                        assumptions=assumptions,
                        confidence_class=spec.confidence_class,
                        source_timestamp=spec.source_timestamp,
                        git_commit=spec.git_commit,
                    ),
                    evidence_context_id=manifest.evidence_context_id,
                    evidence_package_id=manifest.evidence_package_id,
                    layer_id=spec.layer_id,
                    title_th=title_th,
                    title_en=title_en,
                    role_visibility=list(spec.role_visibility),
                    format="geojson",
                    url=(
                        f"/api/v1/layer-data/{spec.layer_id}"
                        f"?study_area={MAE_SAI_STUDY_AREA}"
                    ),
                    data_state="unavailable" if bundle_error else "stale",
                    model_run_id=None,
                    evidence_state=spec.evidence_state,
                    source_components=self._source_components(
                        manifest, spec.source_component_ids
                    ),
                    attribution=list(spec.attribution),
                )
            )
        public_source_ids = (
            "sentinel1-flood-context",
            "hdx-cod-ab-boundaries",
            "worldpop-2020",
            "osm-geofabrik-2026-07-09",
            "copernicus-dem-glo30",
        )
        result.append(
            LayerCatalogItem(
                **self._common(
                    source_name="FloodGuard reduced public preparedness projection",
                    assumptions=[
                        "Historic area-level planning context only; current conditions "
                        "are not confirmed.",
                        "Staff-only road, facility, access, and scoring-component "
                        "details are omitted.",
                    ],
                    confidence_class="low",
                    source_timestamp=manifest.source_timestamp,
                    git_commit=manifest.git_commit,
                ),
                evidence_context_id=manifest.evidence_context_id,
                evidence_package_id=manifest.evidence_package_id,
                layer_id="public_preparedness_areas",
                title_th="พื้นที่เตรียมพร้อมสาธารณะ",
                title_en="Public preparedness areas",
                role_visibility=["public"],
                format="geojson",
                url=(
                    "/api/v1/layer-data/public_preparedness_areas"
                    f"?study_area={MAE_SAI_STUDY_AREA}&role=public"
                ),
                data_state="unavailable" if public_error else "stale",
                model_run_id=None,
                evidence_state=EvidenceState(
                    evidence_type="modelled",
                    granularity="area_summary",
                    confidence_class="low",
                    confidence_reason=(
                        "Historic candidate evidence has not passed qualified "
                        "real-event validation."
                    ),
                    permitted_use="public_preparedness",
                    required_gate="local_current_condition_confirmation",
                    gate_state="blocked",
                ),
                source_components=self._source_components(manifest, public_source_ids),
                attribution=[
                    "Copernicus Data Space Ecosystem",
                    "Copernicus Sentinel-1",
                    "HDX Thailand COD-AB",
                    "WorldPop 2020",
                    "OpenStreetMap contributors",
                    "Geofabrik",
                    "Copernicus DEM GLO-30",
                    "FloodGuard",
                ],
            )
        )
        return result

    def layer_data(self, layer_id: str) -> dict[str, Any]:
        if layer_id == "public_preparedness_areas":
            return self._public_preparedness_layer()
        manifest = self._manifest()
        spec = self._layer_spec(manifest, layer_id)
        payload = deepcopy(self._validated_layer(manifest, spec))
        for feature in payload["features"]:
            properties = feature["properties"]
            properties["area_id"] = str(properties[spec.join_key])
            properties["dataset_mode"] = "candidate"
            properties["operational_status"] = "non_operational"
            properties["official_warning"] = False
            properties["can_feed_decision_layer"] = False
            properties["reason_blocked"] = spec.reason_blocked
            if layer_id == "facilities":
                properties["verification_status"] = "open_context_candidate"
                properties["emergency_role"] = "no_confirmed_emergency_role"
                properties["operating_status"] = "unverified"
                properties["public_visibility"] = False
            elif layer_id == "road_risk" or layer_id == "access_hotspots":
                properties["observation_status"] = "modelled_candidate_not_observed"
            elif layer_id == "priority_areas":
                properties["decision_eligibility"] = "blocked_candidate"
        payload["floodguard_metadata"] = {
            "schema_version": "1.0",
            "study_area_id": manifest.study_area_id,
            "evidence_context_id": manifest.evidence_context_id,
            "dataset_mode": manifest.dataset_mode,
            "operational_status": manifest.operational_status,
            "official_warning": manifest.official_warning,
            "data_version": manifest.data_version,
            "artifact_sha256": spec.sha256,
            "source_timestamp": spec.source_timestamp.isoformat(),
            "confidence_class": spec.confidence_class,
            "processing_allowed": spec.processing_allowed,
            "can_feed_decision_layer": spec.can_feed_decision_layer,
            "reason_blocked": spec.reason_blocked,
            "evidence_state": spec.evidence_state.model_dump(mode="json"),
            "source_components": [
                item.model_dump(mode="json")
                for item in self._source_components(manifest, spec.source_component_ids)
            ],
            "attribution": list(spec.attribution),
        }
        return payload

    def layer_artifact_sha256(self, layer_id: str) -> str:
        if layer_id == "public_preparedness_areas":
            self._validated_public_projection()
            return MAE_SAI_PUBLIC_PROJECTION_SHA256
        manifest = self._manifest()
        spec = self._layer_spec(manifest, layer_id)
        self._validated_layer(manifest, spec)
        return spec.sha256

    def _public_preparedness_layer(self) -> dict[str, Any]:
        """Read the dedicated Public projection without opening a staff artifact."""

        return deepcopy(self._validated_public_projection())

    @staticmethod
    def _source_components(
        manifest: StudyAreaBundleManifest,
        component_ids: tuple[str, ...],
    ) -> list[SourceComponent]:
        requested = set(component_ids)
        return [
            component
            for component in manifest.source_components
            if component.source_component_id in requested
        ]

    def brief(self, area_id: str) -> BriefResponse:
        area = self.area(area_id)
        content = "\n".join(
            [
                f"# Mae Sai candidate action brief — {area.area_name_en} ({area.area_id})",
                "",
                "## สถานะ / Status",
                "",
                "- ชุดข้อมูลผู้สมัครที่ไม่ใช่ระบบปฏิบัติการ",
                "- Historic candidate dataset; non-operational and not an official warning.",
                f"- FPPS: {area.fpps_0_100:.2f}; action class: {area.action_class.value}",
                f"- Confidence: {area.confidence_class.value}",
                "",
                "## Evidence / หลักฐาน",
                "",
                f"- {area.top_reason}",
                (
                    "- People losing modeled 30-minute nearest-facility access: "
                    f"{area.people_losing_30_min_access}"
                ),
                f"- Modelled road candidates: {area.road_evidence.at_risk_segments}",
                f"- Bridge-tagged ways: {area.road_evidence.bridge_count}",
                f"- Open-context facility candidates: {area.facility_evidence.facility_count}",
                "",
                "## Safety boundary / ขอบเขตความปลอดภัย",
                "",
                "- Roads are modelled candidates, not observed closures.",
                "- Facilities are unverified and are not designated evacuation shelters.",
                "- Access uses nearest-facility shortest paths, not 2SFCA.",
                "- Field and agency verification are required before operational use.",
                "",
            ]
        )
        return BriefResponse(
            **self._common(
                source_name="FloodGuard Mae Sai candidate brief adapter",
                assumptions=list(area.assumptions),
                confidence_class="low",
                source_timestamp=area.source_timestamp,
            ),
            area_id=area_id,
            file_name=f"mae_sai_candidate_action_brief_{area_id}.md",
            bilingual=True,
            media_type="text/markdown; charset=utf-8",
            content_markdown=content,
        )

    def scenarios(self) -> list[ScenarioDefinition]:
        """Advertise the closed registry only while its immutable inputs validate."""

        try:
            self._scenario_inputs()
        except ArtifactUnavailable:
            return []
        return definitions(MAE_SAI_STUDY_AREA)

    def run_scenario(self, request: ScenarioRunRequest) -> ScenarioRunResponse:
        """Run candidate access/equity scenarios without recalculating FPPS."""

        if request.study_area != MAE_SAI_STUDY_AREA:
            raise ArtifactNotFound(f"Unknown study_area: {request.study_area}")
        population, edges, facilities, manifest = self._scenario_inputs()
        run_id = run_id_for(request)
        cached = self._scenario_cache.get(run_id)
        if cached is not None:
            return cached

        try:
            baseline_access, baseline_equity = self._scenario_baseline(
                population,
                edges,
                facilities,
            )
            if request.scenario_id == "add_temporary_shelter":
                scenario_kwargs: dict[str, Any] = {
                    "node_id": request.parameters["node_id"],
                    "facility_id": "TEMP-MAE-SAI-PLANNING-001",
                    "facility_type": "temporary_shelter_candidate",
                }
            else:
                edge = edges.loc[
                    edges["edge_id"].astype(str) == request.parameters["edge_id"]
                ].iloc[0]
                scenario_kwargs = {
                    "from_node": str(edge["from_node"]),
                    "to_node": str(edge["to_node"]),
                }
            scenario = run_access_scenario(
                population,
                edges,
                facilities,
                request.scenario_id,
                baseline_access=baseline_access,
                baseline_equity=baseline_equity,
                **scenario_kwargs,
            )
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            raise ArtifactUnavailable(
                "Mae Sai candidate scenario inputs failed the deterministic access contract."
            ) from exc

        baseline_access_index = baseline_access.set_index("subdistrict_id")
        baseline_equity_index = baseline_equity.set_index("subdistrict_id")
        scenario_access_index = scenario["access_loss"].set_index("subdistrict_id")
        scenario_equity_index = scenario["equity_gap"].set_index("subdistrict_id")
        area_results: list[ScenarioAreaResult] = []
        for area_id in sorted(baseline_access_index.index.astype(str)):
            baseline_people = _whole_number(
                baseline_access_index.loc[area_id, "people_losing_30_min_access"]
            )
            scenario_people = _whole_number(
                scenario_access_index.loc[area_id, "people_losing_30_min_access"]
            )
            baseline_ratio = _optional_number(
                baseline_equity_index.loc[area_id, "equity_gap_ratio"]
            )
            scenario_ratio = _optional_number(
                scenario_equity_index.loc[area_id, "equity_gap_ratio"]
            )
            area_results.append(
                ScenarioAreaResult(
                    area_id=area_id,
                    baseline_people_losing_30_min_access=baseline_people,
                    scenario_people_losing_30_min_access=scenario_people,
                    change_people_losing_30_min_access=scenario_people - baseline_people,
                    baseline_equity_gap_ratio=baseline_ratio,
                    scenario_equity_gap_ratio=scenario_ratio,
                    change_equity_gap_ratio=_optional_delta(
                        scenario_ratio,
                        baseline_ratio,
                    ),
                )
            )

        summary = scenario["scenario_summary"].iloc[0]
        assumptions = [
            *manifest.assumptions,
            "Access uses nearest-facility shortest-path thresholds, not 2SFCA.",
            "FPPS is not recalculated; this result contains access and equity deltas only.",
        ]
        if request.scenario_id == "add_temporary_shelter":
            assumptions.append(
                "Capacity is bounded metadata only and is not used by the access engine."
            )
        else:
            assumptions.append(
                f"{MAE_SAI_CLOSE_EDGE_ID} is a modelled graph edge, not an observed closure."
            )
        result = ScenarioRunResponse(
            **self._common(
                source_name="FloodGuard immutable Mae Sai candidate scenario inputs",
                assumptions=assumptions,
                confidence_class="low",
                source_timestamp=manifest.source_timestamp,
            ),
            run_id=run_id,
            scenario_id=request.scenario_id,
            study_area=MAE_SAI_STUDY_AREA,
            parameters=request.parameters,
            run_status="completed",
            result_state="stale",
            backend_config_version=MAE_SAI_BACKEND_CONFIG_VERSION,
            access_method=ACCESS_METHOD,
            fpps_recalculated=False,
            input_manifest_sha256=MAE_SAI_SCENARIO_MANIFEST_SHA256,
            input_receipt_sha256=manifest.receipt_sha256,
            overall=ScenarioOverallResult(
                baseline_people_losing_30_min_access=_whole_number(
                    summary["baseline_people_losing_30_min_access"]
                ),
                scenario_people_losing_30_min_access=_whole_number(
                    summary["scenario_people_losing_30_min_access"]
                ),
                change_people_losing_30_min_access=_whole_number(
                    summary["change_people_losing_30_min_access"]
                ),
                baseline_max_equity_gap_ratio=_optional_number(
                    summary["baseline_max_equity_gap_ratio"]
                ),
                scenario_max_equity_gap_ratio=_optional_number(
                    summary["scenario_max_equity_gap_ratio"]
                ),
                change_max_equity_gap_ratio=_optional_number_allow_negative(
                    summary["change_max_equity_gap_ratio"]
                ),
            ),
            areas=area_results,
        )
        self._scenario_cache[run_id] = result
        return result

    def _scenario_baseline(
        self,
        population: pd.DataFrame,
        edges: pd.DataFrame,
        facilities: pd.DataFrame,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        if self._baseline_cache is None:
            baseline_access = calculate_access_loss(population, edges, facilities)
            baseline_equity = compute_equity_gap(
                equity_input_from_access_loss(
                    baseline_access,
                    threshold=30,
                    confidence_class="low",
                )
            )
            self._baseline_cache = (baseline_access, baseline_equity)
        return self._baseline_cache

    def _scenario_inputs(
        self,
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, ScenarioInputManifest]:
        manifest = self._scenario_manifest()
        frames: dict[str, pd.DataFrame] = {}
        expected_columns = {
            "population_nodes": {
                "node_id",
                "subdistrict_id",
                "total_population",
                "vulnerable_population",
                "non_vulnerable_population",
            },
            "access_edges": {
                "edge_id",
                "road_id",
                "from_node",
                "to_node",
                "normal_minutes",
                "disrupted_minutes",
                "road_disruption_probability_0_1",
                "candidate_closure_status",
                "subdistrict_id",
                "bridge_flag",
            },
            "facility_candidates": {
                "facility_id",
                "facility_type",
                "amenity",
                "facility_name",
                "longitude",
                "latitude",
                "node_id",
                "snap_distance_m",
                "subdistrict_id",
                "subdistrict_name",
                "source_name",
                "source_timestamp",
                "confidence_class",
                "assumptions",
            },
        }
        for artifact in manifest.artifacts:
            path = (self.paths.outputs / artifact.relative_path).resolve()
            try:
                path.relative_to(self.paths.outputs.resolve())
            except ValueError as exc:
                raise ArtifactUnavailable(
                    "Mae Sai scenario artifact resolves outside the output directory."
                ) from exc
            if not path.is_file() or _sha256(path) != artifact.sha256:
                raise ArtifactUnavailable(
                    f"Mae Sai scenario {artifact.role} checksum validation failed."
                )
            try:
                frame = pd.read_csv(path)
            except (OSError, UnicodeError, pd.errors.ParserError) as exc:
                raise ArtifactUnavailable(
                    f"Mae Sai scenario {artifact.role} is unreadable."
                ) from exc
            if len(frame) != artifact.row_count:
                raise ArtifactUnavailable(
                    f"Mae Sai scenario {artifact.role} row-count validation failed."
                )
            if tuple(frame.columns) != artifact.columns or set(frame.columns) != expected_columns[
                artifact.role
            ]:
                raise ArtifactUnavailable(
                    f"Mae Sai scenario {artifact.role} column validation failed."
                )
            frames[artifact.role] = frame

        population = frames["population_nodes"].copy()
        edges = frames["access_edges"].copy()
        facilities = frames["facility_candidates"].copy()
        expected_area_ids = set(self._manifest().expected_area_ids)
        self._validate_scenario_frame_identities(
            population,
            edges,
            facilities,
            expected_area_ids,
        )
        area_names = {area.area_id: area.area_name_en for area in self.areas()}
        population["subdistrict_name"] = population["subdistrict_id"].astype(str).map(
            area_names
        )
        if population["subdistrict_name"].isna().any():
            raise ArtifactUnavailable("Mae Sai scenario area-name join validation failed.")
        return population, edges, facilities, manifest

    def _scenario_manifest(self) -> ScenarioInputManifest:
        path = self.paths.root / MAE_SAI_SCENARIO_MANIFEST_RELATIVE_PATH
        if not path.is_file() or _sha256(path) != MAE_SAI_SCENARIO_MANIFEST_SHA256:
            raise ArtifactUnavailable("Mae Sai scenario manifest checksum validation failed.")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            receipt_sha256 = payload.get("receipt_sha256")
            unsigned = {key: value for key, value in payload.items() if key != "receipt_sha256"}
            canonical = json.dumps(
                unsigned,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != receipt_sha256:
                raise ValueError("receipt checksum mismatch")
            return ScenarioInputManifest.model_validate(payload)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise ArtifactUnavailable("Mae Sai scenario manifest validation failed.") from exc

    @staticmethod
    def _validate_scenario_frame_identities(
        population: pd.DataFrame,
        edges: pd.DataFrame,
        facilities: pd.DataFrame,
        expected_area_ids: set[str],
    ) -> None:
        for frame, identity, label in (
            (population, "node_id", "population_nodes"),
            (edges, "edge_id", "access_edges"),
            (facilities, "facility_id", "facility_candidates"),
        ):
            values = frame[identity].astype(str)
            if values.str.strip().eq("").any() or (
                label != "population_nodes" and values.duplicated().any()
            ):
                raise ArtifactUnavailable(f"Mae Sai scenario {label} identity validation failed.")
            if not set(frame["subdistrict_id"].astype(str)).issubset(expected_area_ids):
                raise ArtifactUnavailable(f"Mae Sai scenario {label} area join validation failed.")

        for column in (
            "total_population",
            "vulnerable_population",
            "non_vulnerable_population",
        ):
            values = pd.to_numeric(population[column], errors="coerce")
            if values.isna().any() or (values < 0).any():
                raise ArtifactUnavailable("Mae Sai scenario population metric validation failed.")
            population[column] = values
        population_balance = (
            population["vulnerable_population"]
            + population["non_vulnerable_population"]
            - population["total_population"]
        ).abs()
        if (population_balance > 0.002).any():
            raise ArtifactUnavailable("Mae Sai scenario population balance validation failed.")

        normal = pd.to_numeric(edges["normal_minutes"], errors="coerce")
        disrupted = pd.to_numeric(edges["disrupted_minutes"], errors="coerce")
        probability = pd.to_numeric(
            edges["road_disruption_probability_0_1"],
            errors="coerce",
        )
        if normal.isna().any() or (normal <= 0).any():
            raise ArtifactUnavailable("Mae Sai scenario normal-edge time validation failed.")
        if disrupted.dropna().lt(0).any():
            raise ArtifactUnavailable("Mae Sai scenario disrupted-edge time validation failed.")
        if probability.isna().any() or probability.lt(0).any() or probability.gt(1).any():
            raise ArtifactUnavailable("Mae Sai scenario road probability validation failed.")
        edges["normal_minutes"] = normal
        edges["disrupted_minutes"] = disrupted
        edges["road_disruption_probability_0_1"] = probability

        graph_nodes = set(edges["from_node"].astype(str)) | set(edges["to_node"].astype(str))
        if not set(population["node_id"].astype(str)).issubset(graph_nodes):
            raise ArtifactUnavailable("Mae Sai population nodes are outside the scenario graph.")
        if not set(facilities["node_id"].astype(str)).issubset(graph_nodes):
            raise ArtifactUnavailable("Mae Sai facility nodes are outside the scenario graph.")
        if MAE_SAI_TEMPORARY_SHELTER_NODE not in set(population["node_id"].astype(str)):
            raise ArtifactUnavailable("Pinned temporary-facility node is unavailable.")
        selected_edge = edges[edges["edge_id"].astype(str) == MAE_SAI_CLOSE_EDGE_ID]
        if len(selected_edge) != 1 or selected_edge["disrupted_minutes"].isna().any():
            raise ArtifactUnavailable("Pinned road-closure edge is unavailable or already closed.")

    def _common(
        self,
        *,
        source_name: str,
        assumptions: list[str] | tuple[str, ...],
        confidence_class: str,
        source_timestamp: datetime | None = None,
        git_commit: str | None = None,
    ) -> dict[str, Any]:
        try:
            manifest = self._manifest()
        except ArtifactUnavailable:
            data_version = MAE_SAI_DATA_VERSION
            manifest_git_commit = MAE_SAI_DATA_GIT_COMMIT
            manifest_source_timestamp = MAE_SAI_SOURCE_TIMESTAMP
        else:
            data_version = manifest.data_version
            manifest_git_commit = manifest.git_commit
            manifest_source_timestamp = manifest.source_timestamp
        return {
            "schema_version": "1.0",
            "dataset_mode": "candidate",
            "operational_status": "non_operational",
            "source_timestamp": source_timestamp or manifest_source_timestamp,
            "generated_at": self.generated_at,
            "confidence_class": confidence_class,
            "source_name": source_name,
            "assumptions": _unique_strings(list(assumptions)),
            "official_warning": False,
            "data_version": data_version,
            "git_commit": git_commit or manifest_git_commit,
        }

    def _manifest(self) -> StudyAreaBundleManifest:
        path = self.manifest_path
        if not path.is_file():
            raise ArtifactUnavailable("Mae Sai bundle manifest is unavailable.")
        actual_sha256 = _sha256(path)
        if actual_sha256 != MAE_SAI_MANIFEST_SHA256:
            raise ArtifactUnavailable("Mae Sai bundle manifest checksum validation failed.")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return StudyAreaBundleManifest.model_validate(payload)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise ArtifactUnavailable("Mae Sai bundle manifest validation failed.") from exc

    def _validated_public_projection(self) -> dict[str, Any]:
        """Validate the dedicated Public artifact without loading staff GeoJSON bytes."""

        manifest = self._manifest()
        path = self.public_projection_path.resolve()
        try:
            path.relative_to(self.paths.root.resolve())
        except ValueError as exc:
            raise ArtifactUnavailable(
                "Mae Sai Public projection resolves outside the repository."
            ) from exc
        if not path.is_file():
            raise ArtifactUnavailable("Mae Sai Public projection is unavailable.")
        if _sha256(path) != MAE_SAI_PUBLIC_PROJECTION_SHA256:
            raise ArtifactUnavailable(
                "Mae Sai Public projection checksum validation failed."
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ArtifactUnavailable("Mae Sai Public projection is unreadable.") from exc
        if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
            raise ArtifactUnavailable("Mae Sai Public projection is not a FeatureCollection.")
        features = payload.get("features")
        if not isinstance(features, list) or len(features) != len(manifest.expected_area_ids):
            raise ArtifactUnavailable(
                "Mae Sai Public projection feature-count validation failed."
            )
        allowed_properties = {
            "schema_version",
            "evidence_context_id",
            "area_id",
            "area_name_th",
            "area_name_en",
            "planning_priority_0_100",
            "evidence_sufficiency",
            "recommendation_code",
            "source_timestamp",
            "freshness",
            "current_conditions_confirmed",
        }
        observed_area_ids: set[str] = set()
        min_x, min_y, max_x, max_y = manifest.expected_bounds
        for index, feature in enumerate(features):
            if not isinstance(feature, dict) or feature.get("type") != "Feature":
                raise ArtifactUnavailable(
                    f"Mae Sai Public projection feature {index} is invalid."
                )
            properties = feature.get("properties")
            geometry = feature.get("geometry")
            if (
                not isinstance(properties, dict)
                or set(properties) != allowed_properties
                or not isinstance(geometry, dict)
            ):
                raise ArtifactUnavailable(
                    "Mae Sai Public projection contains non-public fields."
                )
            try:
                record = PublicPreparednessArea.model_validate(properties)
            except ValueError as exc:
                raise ArtifactUnavailable(
                    "Mae Sai Public projection record validation failed."
                ) from exc
            if (
                record.evidence_context_id != manifest.evidence_context_id
                or record.current_conditions_confirmed
                or record.area_id in observed_area_ids
            ):
                raise ArtifactUnavailable(
                    "Mae Sai Public projection evidence identity is invalid."
                )
            observed_area_ids.add(record.area_id)
            positions = list(_iter_positions(geometry.get("coordinates")))
            if geometry.get("type") != "MultiPolygon" or not positions:
                raise ArtifactUnavailable(
                    "Mae Sai Public projection geometry type is invalid."
                )
            for longitude, latitude in positions:
                if (
                    not math.isfinite(longitude)
                    or not math.isfinite(latitude)
                    or not (min_x <= longitude <= max_x)
                    or not (min_y <= latitude <= max_y)
                ):
                    raise ArtifactUnavailable(
                        "Mae Sai Public projection geometry is outside declared bounds."
                    )
        if observed_area_ids != set(manifest.expected_area_ids):
            raise ArtifactUnavailable("Mae Sai Public projection area coverage is incomplete.")

        metadata = payload.get("floodguard_metadata")
        priority_spec = self._layer_spec(manifest, "priority_areas")
        if not isinstance(metadata, dict):
            raise ArtifactUnavailable("Mae Sai Public projection metadata is missing.")
        source_components = metadata.get("source_components")
        evidence_state = metadata.get("evidence_state")
        component_ids = {
            str(component.get("source_component_id"))
            for component in source_components
            if isinstance(component, dict)
        } if isinstance(source_components, list) else set()
        if (
            metadata.get("study_area_id") != manifest.study_area_id
            or metadata.get("evidence_context_id") != manifest.evidence_context_id
            or metadata.get("evidence_package_id") != manifest.evidence_package_id
            or metadata.get("dataset_mode") != manifest.dataset_mode
            or metadata.get("operational_status") != manifest.operational_status
            or metadata.get("official_warning") is not False
            or metadata.get("data_version") != manifest.data_version
            or metadata.get("artifact_sha256") != priority_spec.sha256
            or metadata.get("role_visibility") != ["public"]
            or component_ids != set(priority_spec.source_component_ids)
            or not isinstance(evidence_state, dict)
            or evidence_state.get("permitted_use")
            != "public_preparedness"
        ):
            raise ArtifactUnavailable(
                "Mae Sai Public projection lineage metadata validation failed."
            )
        required_attribution = {
            attribution
            for component in manifest.source_components
            if component.source_component_id in priority_spec.source_component_ids
            for attribution in component.attribution
        }
        attribution = metadata.get("attribution")
        if not isinstance(attribution, list) or not required_attribution.issubset(
            set(attribution)
        ):
            raise ArtifactUnavailable(
                "Mae Sai Public projection attribution is incomplete."
            )
        return payload

    def _validated_layers(self) -> dict[str, dict[str, Any]]:
        manifest = self._manifest()
        result: dict[str, dict[str, Any]] = {}
        for spec in manifest.layers:
            result[spec.layer_id] = self._validated_layer(manifest, spec)
        return result

    def _validated_layer(
        self,
        manifest: StudyAreaBundleManifest,
        spec: BundleLayerSpec,
    ) -> dict[str, Any]:
        path = (self.paths.root / Path(spec.relative_path)).resolve()
        try:
            path.relative_to(self.paths.root.resolve())
        except ValueError as exc:
            raise ArtifactUnavailable(
                f"Layer {spec.layer_id} resolves outside the repository."
            ) from exc
        if not path.is_file():
            raise ArtifactUnavailable(f"Layer {spec.layer_id} is unavailable.")
        if _sha256(path) != spec.sha256:
            raise ArtifactUnavailable(f"Layer {spec.layer_id} checksum validation failed.")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ArtifactUnavailable(f"Layer {spec.layer_id} is unreadable GeoJSON.") from exc
        if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
            raise ArtifactUnavailable(f"Layer {spec.layer_id} is not a FeatureCollection.")
        features = payload.get("features")
        if not isinstance(features, list) or len(features) != spec.expected_feature_count:
            raise ArtifactUnavailable(f"Layer {spec.layer_id} feature-count validation failed.")

        expected_area_ids = set(manifest.expected_area_ids)
        observed_area_ids: set[str] = set()
        primary_ids: set[str] = set()
        primary_key = {
            "administrative_boundaries": "subdistrict_id",
            "priority_areas": "subdistrict_id",
            "road_risk": "road_id",
            "facilities": "facility_id",
            "access_hotspots": "subdistrict_id",
        }[spec.layer_id]
        for index, feature in enumerate(features):
            if not isinstance(feature, dict) or feature.get("type") != "Feature":
                raise ArtifactUnavailable(
                    f"Layer {spec.layer_id} feature {index} is not a GeoJSON Feature."
                )
            properties = feature.get("properties")
            geometry = feature.get("geometry")
            if not isinstance(properties, dict) or not isinstance(geometry, dict):
                raise ArtifactUnavailable(f"Layer {spec.layer_id} has an incomplete feature.")
            missing = [name for name in spec.required_properties if name not in properties]
            if missing:
                raise ArtifactUnavailable(
                    f"Layer {spec.layer_id} is missing contracted properties."
                )
            geometry_type = geometry.get("type")
            if geometry_type not in spec.geometry_types:
                raise ArtifactUnavailable(f"Layer {spec.layer_id} geometry type is invalid.")
            positions = list(_iter_positions(geometry.get("coordinates")))
            if not positions:
                raise ArtifactUnavailable(f"Layer {spec.layer_id} has empty geometry.")
            for longitude, latitude in positions:
                if not (math.isfinite(longitude) and math.isfinite(latitude)):
                    raise ArtifactUnavailable(
                        f"Layer {spec.layer_id} contains a non-finite coordinate."
                    )
                min_x, min_y, max_x, max_y = manifest.expected_bounds
                if not (min_x <= longitude <= max_x and min_y <= latitude <= max_y):
                    raise ArtifactUnavailable(
                        f"Layer {spec.layer_id} contains geometry outside declared bounds."
                    )
            area_id = _required_text(properties.get(spec.join_key), "")
            if area_id not in expected_area_ids:
                raise ArtifactUnavailable(f"Layer {spec.layer_id} has an unknown area join key.")
            observed_area_ids.add(area_id)
            primary_id = _required_text(properties.get(primary_key), "")
            if not primary_id or primary_id in primary_ids:
                raise ArtifactUnavailable(f"Layer {spec.layer_id} feature identity is invalid.")
            primary_ids.add(primary_id)
            if _contains_true_official_warning(properties):
                raise ArtifactUnavailable(
                    f"Layer {spec.layer_id} contains an unsupported official-warning claim."
                )
            self._validate_layer_semantics(spec.layer_id, properties)

        if spec.layer_id in {
            "administrative_boundaries",
            "priority_areas",
            "access_hotspots",
        } and observed_area_ids != expected_area_ids:
            raise ArtifactUnavailable(f"Layer {spec.layer_id} area coverage is incomplete.")
        return payload

    @staticmethod
    def _validate_layer_semantics(layer_id: str, properties: dict[str, Any]) -> None:
        if layer_id == "facilities":
            if properties.get("candidate_status") != "unverified_osm_candidate":
                raise ArtifactUnavailable("Facility verification state substitution was rejected.")
            warning = str(properties.get("warning_text", "")).lower()
            if "not a confirmed" not in warning:
                raise ArtifactUnavailable("Facility warning contract is invalid.")
        elif layer_id == "road_risk":
            probability = _number_in_range(
                properties.get("road_disruption_probability_0_1"),
                minimum=0,
                maximum=1,
            )
            del probability
            warning = str(properties.get("warning_text", "")).lower()
            if "not an observed closure" not in warning:
                raise ArtifactUnavailable("Road observation warning contract is invalid.")
        elif layer_id == "priority_areas":
            for field in (
                "flood_likelihood_0_100",
                "exposure_0_100",
                "access_gap_0_100",
                "road_criticality_0_100",
                "vulnerability_context_0_100",
                "fpps_0_100",
            ):
                _number_in_range(properties.get(field), minimum=0, maximum=100)
            if properties.get("confidence_class") != "low":
                raise ArtifactUnavailable(
                    "Candidate decision confidence substitution was rejected."
                )

    @staticmethod
    def _layer_spec(
        manifest: StudyAreaBundleManifest,
        layer_id: str,
    ) -> BundleLayerSpec:
        for spec in manifest.layers:
            if spec.layer_id == layer_id:
                return spec
        raise ArtifactNotFound(f"Unknown layer_id for {MAE_SAI_STUDY_AREA}: {layer_id}")


class DatasetRegistry:
    """Dispatch typed requests to one explicitly selected immutable dataset adapter."""

    def __init__(
        self,
        paths: RepositoryPaths | None = None,
        fixture_repository: ArtifactRepository | None = None,
    ) -> None:
        resolved_paths = paths or RepositoryPaths.discover()
        self.fixture = fixture_repository or ArtifactRepository(resolved_paths)
        self.mae_sai = MaeSaiCandidateAdapter(resolved_paths)

    def _adapter(self, study_area: str) -> ArtifactRepository | MaeSaiCandidateAdapter:
        if study_area == FIXTURE_STUDY_AREA:
            return self.fixture
        if study_area == MAE_SAI_STUDY_AREA:
            return self.mae_sai
        raise ArtifactNotFound(f"Unknown study_area: {study_area}")

    def status(self, study_area: str = FIXTURE_STUDY_AREA) -> StatusResponse:
        adapter = self._adapter(study_area)
        if isinstance(adapter, ArtifactRepository):
            return adapter.status(study_area)
        return adapter.status()

    def study_areas(self) -> list[StudyArea]:
        return [*self.fixture.study_areas(), self.mae_sai.study_area()]

    def areas(self, study_area: str = FIXTURE_STUDY_AREA) -> list[AreaDecision]:
        adapter = self._adapter(study_area)
        if isinstance(adapter, ArtifactRepository):
            return adapter.areas(study_area)
        return adapter.areas()

    def public_areas(
        self,
        study_area: str = FIXTURE_STUDY_AREA,
    ) -> list[PublicPreparednessArea]:
        adapter = self._adapter(study_area)
        return adapter.public_areas()

    def evidence_context(
        self,
        study_area: str = FIXTURE_STUDY_AREA,
    ) -> EvidenceContext:
        adapter = self._adapter(study_area)
        return adapter.evidence_context()

    def evidence_record(self, evidence_context_id: str) -> EvidenceRecord:
        for study_area in (FIXTURE_STUDY_AREA, MAE_SAI_STUDY_AREA):
            adapter = self._adapter(study_area)
            context = adapter.evidence_context()
            if context.evidence_context_id == evidence_context_id:
                return adapter.evidence_record()
        raise ArtifactNotFound(f"Unknown evidence_context_id: {evidence_context_id}")

    def area(self, area_id: str, study_area: str = FIXTURE_STUDY_AREA) -> AreaDecision:
        adapter = self._adapter(study_area)
        if isinstance(adapter, ArtifactRepository):
            return adapter.area(area_id, study_area)
        return adapter.area(area_id)

    def layers(
        self,
        study_area: str = FIXTURE_STUDY_AREA,
        role: Literal["public", "command", "studio"] = "command",
    ) -> list[LayerCatalogItem]:
        adapter = self._adapter(study_area)
        if isinstance(adapter, ArtifactRepository):
            layers = adapter.layers(study_area)
        else:
            layers = adapter.layers(role)
        return visible_layers_for_role(layers, role)

    def layer_data(
        self,
        layer_id: str,
        study_area: str = FIXTURE_STUDY_AREA,
        role: Literal["public", "command", "studio"] = "command",
    ) -> dict[str, Any]:
        adapter = self._adapter(study_area)
        visible_ids = {item.layer_id for item in self.layers(study_area, role)}
        if layer_id not in visible_ids:
            raise ArtifactNotFound(
                f"Layer {layer_id} is not available for role {role} in {study_area}."
            )
        if isinstance(adapter, ArtifactRepository):
            return adapter.layer_data(layer_id, study_area)
        return adapter.layer_data(layer_id)

    def layer_artifact_sha256(
        self,
        layer_id: str,
        study_area: str = FIXTURE_STUDY_AREA,
    ) -> str:
        adapter = self._adapter(study_area)
        if isinstance(adapter, ArtifactRepository):
            return adapter.layer_artifact_sha256(layer_id, study_area)
        return adapter.layer_artifact_sha256(layer_id)

    def brief(self, area_id: str, study_area: str = FIXTURE_STUDY_AREA) -> BriefResponse:
        adapter = self._adapter(study_area)
        if isinstance(adapter, ArtifactRepository):
            return adapter.brief(area_id, study_area)
        return adapter.brief(area_id)

    def scenarios(self, study_area: str = FIXTURE_STUDY_AREA) -> list[ScenarioDefinition]:
        adapter = self._adapter(study_area)
        if study_area == MAE_SAI_STUDY_AREA:
            assert isinstance(adapter, MaeSaiCandidateAdapter)
            return adapter.scenarios()
        return definitions()

    def run_scenario(self, request: ScenarioRunRequest) -> ScenarioRunResponse:
        if request.study_area == MAE_SAI_STUDY_AREA:
            return self.mae_sai.run_scenario(request)
        return self.fixture.run_scenario(request)

    def model_runs(self) -> list[ModelRun]:
        return self.fixture.model_runs()

    def model_run(self, run_id: str) -> ModelRun:
        return self.fixture.model_run(run_id)

    def readiness(self) -> list[ReadinessItem]:
        return self.fixture.readiness()


def visible_layers_for_role(
    layers: list[LayerCatalogItem],
    role: Literal["public", "command", "studio"],
) -> list[LayerCatalogItem]:
    """Return only layers whose immutable catalog explicitly permits the role."""

    return [item for item in layers if role in item.role_visibility]


def filter_geojson_payload(
    payload: dict[str, Any],
    *,
    layer_id: str,
    area_id: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    facility_type: str | None = None,
    verification_status: str | None = None,
    minimum_risk: float = 0,
    detail: Literal["regional", "selected_area"] = "regional",
) -> dict[str, Any]:
    """Apply bounded server-side filters without mutating the validated artifact."""

    if detail == "selected_area" and not area_id:
        raise LayerFilterError("detail=selected_area requires area_id")
    if facility_type is not None and layer_id != "facilities":
        raise LayerFilterError("facility_type is valid only for the facilities layer")
    if verification_status is not None and layer_id != "facilities":
        raise LayerFilterError("verification_status is valid only for the facilities layer")
    if minimum_risk and layer_id != "road_risk":
        raise LayerFilterError("minimum_risk is valid only for the road_risk layer")
    if bbox is not None:
        min_x, min_y, max_x, max_y = bbox
        if max_x <= min_x or max_y <= min_y:
            raise LayerFilterError("bbox must have positive area")
        if not (-180 <= min_x < max_x <= 180 and -90 <= min_y < max_y <= 90):
            raise LayerFilterError("bbox must be valid WGS84 coordinates")

    result = deepcopy(payload)
    selected: list[dict[str, Any]] = []
    for feature in result.get("features", []):
        properties = feature.get("properties", {})
        if area_id is not None and str(properties.get("area_id")) != area_id:
            continue
        if facility_type is not None and properties.get("facility_type") != facility_type:
            continue
        if (
            verification_status is not None
            and properties.get("verification_status") != verification_status
        ):
            continue
        if layer_id == "road_risk" and float(
            properties.get("road_disruption_probability_0_1", 0)
        ) < minimum_risk:
            continue
        if bbox is not None and not _geometry_intersects_bbox(feature.get("geometry"), bbox):
            continue
        selected.append(feature)

    if layer_id == "road_risk" and detail == "regional" and area_id is None:
        selected.sort(
            key=lambda feature: (
                bool(feature.get("properties", {}).get("bridge_flag")),
                float(
                    feature.get("properties", {}).get(
                        "road_disruption_probability_0_1", 0
                    )
                ),
                str(feature.get("properties", {}).get("road_id", "")),
            ),
            reverse=True,
        )
        selected = selected[:750]
    result["features"] = selected
    result.setdefault("floodguard_query", {})
    result["floodguard_query"] = {
        "area_id": area_id,
        "bbox": list(bbox) if bbox is not None else None,
        "facility_type": facility_type,
        "verification_status": verification_status,
        "minimum_risk": minimum_risk,
        "detail": detail,
        "returned_feature_count": len(selected),
    }
    return result


def parse_bbox(value: str | None) -> tuple[float, float, float, float] | None:
    """Parse a compact WGS84 bbox query or fail with a sanitized client error."""

    if value is None:
        return None
    try:
        values = tuple(float(part.strip()) for part in value.split(","))
    except ValueError as exc:
        raise LayerFilterError("bbox must contain four comma-separated numbers") from exc
    if len(values) != 4:
        raise LayerFilterError("bbox must contain four comma-separated numbers")
    return values  # type: ignore[return-value]


def _iter_positions(value: Any) -> Any:
    if (
        isinstance(value, list)
        and len(value) >= 2
        and isinstance(value[0], int | float)
        and not isinstance(value[0], bool)
        and isinstance(value[1], int | float)
        and not isinstance(value[1], bool)
    ):
        yield float(value[0]), float(value[1])
        return
    if isinstance(value, list):
        for item in value:
            yield from _iter_positions(item)


def _geometry_intersects_bbox(
    geometry: Any,
    bbox: tuple[float, float, float, float],
) -> bool:
    if not isinstance(geometry, dict):
        return False
    positions = list(_iter_positions(geometry.get("coordinates")))
    if not positions:
        return False
    min_x = min(position[0] for position in positions)
    min_y = min(position[1] for position in positions)
    max_x = max(position[0] for position in positions)
    max_y = max(position[1] for position in positions)
    return not (
        max_x < bbox[0] or max_y < bbox[1] or min_x > bbox[2] or min_y > bbox[3]
    )


def _contains_true_official_warning(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            (key == "official_warning" and item is True)
            or _contains_true_official_warning(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_true_official_warning(item) for item in value)
    return False


def _number_in_range(value: Any, *, minimum: float, maximum: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ArtifactUnavailable("Candidate layer contains a non-numeric metric.") from exc
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ArtifactUnavailable("Candidate layer contains an out-of-range metric.")
    return result


def _optional_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and result >= 0 else None


def _optional_number_allow_negative(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return round(result, 6) if math.isfinite(result) else None


def _optional_delta(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None:
        return None
    return round(value - baseline, 6)


def _whole_number(value: Any) -> int:
    return int(round(float(value)))


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        try:
            result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ArtifactUnavailable("Candidate source timestamp is invalid.") from exc
    if result.tzinfo is None:
        raise ArtifactUnavailable("Candidate source timestamp must include a timezone.")
    return result


def _required_text(value: Any, fallback: str) -> str:
    text = "" if value is None else str(value).strip()
    return text or fallback


def _unique_strings(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = _required_text(value, "")
        if text and text not in result:
            result.append(text)
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
