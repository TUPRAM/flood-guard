"""Read committed artifacts and adapt them to the public API contracts."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from functools import cached_property
from pathlib import Path
from typing import Any

import pandas as pd
from floodguard.access import calculate_access_loss
from floodguard.briefs import build_action_brief
from floodguard.equity import compute_equity_gap, equity_input_from_access_loss
from floodguard.scenarios import run_access_scenario

from floodguard_api.config import RepositoryPaths
from floodguard_api.models import (
    AreaDecision,
    BriefResponse,
    DataState,
    FacilityEvidence,
    LayerCatalogItem,
    ModelRun,
    ReadinessItem,
    RoadEvidence,
    ScenarioAreaResult,
    ScenarioOverallResult,
    ScenarioRunRequest,
    ScenarioRunResponse,
    StatusResponse,
    StudyArea,
)
from floodguard_api.scenario_registry import (
    ACCESS_METHOD,
    BACKEND_CONFIG_VERSION,
    run_id_for,
)

DATA_GIT_COMMIT = "58cb508acbfac43a21cf347259cf6d12beef533c"
FIXTURE_DATA_VERSION = "fixture-2026-06-29-v1"
FIXTURE_SOURCE_TIMESTAMP = datetime(2026, 6, 29, tzinfo=UTC)
WEAK_SOURCE_TIMESTAMP = datetime(2024, 9, 15, 23, 16, 1, tzinfo=UTC)

_THAI_AREA_NAMES = {
    "FG-TB-001": "ตลาดริมน้ำ (พื้นที่สาธิต)",
    "FG-TB-002": "ชุมทางสะพาน (พื้นที่สาธิต)",
    "FG-TB-003": "แอ่งคลินิก (พื้นที่สาธิต)",
    "FG-TB-004": "ชายคลอง (พื้นที่สาธิต)",
    "FG-TB-005": "เนินเขาที่ยังไม่ยืนยัน (พื้นที่สาธิต)",
}

_PRIORITY_COLUMNS = frozenset(
    {
        "subdistrict_id",
        "subdistrict_name",
        "fpps_0_100",
        "action_class",
        "top_reason",
        "confidence_class",
        "source_name",
        "source_timestamp",
        "assumptions",
    }
)
_POPULATION_INPUT_COLUMNS = frozenset(
    {
        "subdistrict_id",
        "subdistrict_name",
        "flood_likelihood_0_100",
        "exposure_0_100",
        "access_gap_0_100",
        "road_criticality_0_100",
        "vulnerability_context_0_100",
        "confidence_class",
        "source_name",
        "source_timestamp",
        "assumptions",
    }
)
_ACCESS_COLUMNS = frozenset({"subdistrict_id", "people_losing_30_min_access"})
_EQUITY_COLUMNS = frozenset({"subdistrict_id", "equity_gap_ratio"})
_ROAD_RISK_COLUMNS = frozenset({"road_id", "subdistrict_id"})
_FACILITY_COLUMNS = frozenset({"facility_id", "facility_type", "node_id"})
_SCENARIO_POPULATION_COLUMNS = frozenset(
    {
        "node_id",
        "subdistrict_id",
        "subdistrict_name",
        "total_population",
        "vulnerable_population",
        "non_vulnerable_population",
    }
)
_SCENARIO_EDGE_COLUMNS = frozenset({"from_node", "to_node", "normal_minutes", "disrupted_minutes"})
_READINESS_COLUMNS = frozenset(
    {
        "check_id",
        "phase",
        "status",
        "severity",
        "observed",
        "required",
        "blocker",
        "source_timestamp",
        "confidence_class",
        "assumptions",
    }
)
_SYNTHETIC_METRIC_COLUMNS = frozenset({"iou", "f1_dice", "precision", "recall", "area_error_ratio"})
_SYNTHETIC_PROBABILITY_COLUMNS = frozenset({"flood_probability_0_1", "reference_flood_extent"})
_SYNTHETIC_INPUT_COLUMNS = frozenset(
    {
        "pixel_id",
        "row",
        "col",
        "pre_vv_db",
        "post_vv_db",
        "pre_vh_db",
        "post_vh_db",
        "reference_flood_extent",
    }
)
_WEAK_METRIC_COLUMNS = frozenset(
    {
        "experiment_name",
        "feature_columns",
        "decision_threshold",
        "ml_iou",
        "ml_f1_dice",
        "ml_precision",
        "ml_recall",
        "ml_area_error_ratio",
    }
)
_WEAK_FEATURE_COLUMNS = frozenset(
    {
        "pre_product_id",
        "post_product_id",
        "reference_product_id",
        "reference_status",
        "sample_width",
        "sample_height",
        "bbox_lon_min",
        "bbox_lat_min",
        "bbox_lon_max",
        "bbox_lat_max",
    }
)
_ACQUISITION_COLUMNS = frozenset({"product_id", "sha256", "acquisition_date"})
_REFERENCE_COLUMNS = frozenset({"reference_id", "sha256"})


class ArtifactUnavailable(RuntimeError):
    """Raised when a required, small committed artifact is unavailable."""


class ArtifactNotFound(LookupError):
    """Raised when a stable artifact ID does not exist."""


class ArtifactRepository:
    """Repository-backed adapter with no network or private-data dependency."""

    def __init__(self, paths: RepositoryPaths | None = None) -> None:
        self.paths = paths or RepositoryPaths.discover()
        self.generated_at = datetime.now(UTC)

    @staticmethod
    def _require_fixture_study_area(study_area: str) -> None:
        """Reject cross-dataset substitution when this fixture adapter is used directly."""

        if study_area != "fixture_thailand_demo":
            raise ArtifactNotFound(f"Unknown study_area: {study_area}")

    @property
    def required_decision_artifacts(self) -> tuple[Path, ...]:
        return (
            self.paths.outputs / "sample_priority_scores.csv",
            self.paths.fixtures / "sample_population.csv",
            self.paths.outputs / "sample_access_loss.csv",
            self.paths.outputs / "sample_equity_gap.csv",
            self.paths.outputs / "sample_road_risk.csv",
            self.paths.outputs / "priority_subdistricts.geojson",
            self.paths.fixtures / "sample_facilities.csv",
        )

    @property
    def required_scenario_artifacts(self) -> tuple[Path, ...]:
        return (
            self.paths.fixtures / "sample_population_nodes.csv",
            self.paths.fixtures / "sample_access_edges.csv",
            self.paths.fixtures / "sample_facilities.csv",
        )

    def status(self, study_area: str = "fixture_thailand_demo") -> StatusResponse:
        self._require_fixture_study_area(study_area)
        decision_blocker = self._decision_artifact_blocker()
        scenario_blocker = self._scenario_artifact_blocker()
        if decision_blocker:
            data_state = DataState.UNAVAILABLE
            assumptions = [
                "One or more required committed fixture artifacts are unavailable or invalid.",
                decision_blocker,
            ]
            message_en = "Fixture data unavailable; the API process itself remains healthy."
            message_th = "ข้อมูลสาธิตไม่พร้อมใช้งาน แต่บริการ API ยังทำงานอยู่"
        elif scenario_blocker:
            data_state = DataState.BLOCKED
            assumptions = [
                "Core fixture decisions remain available.",
                scenario_blocker,
            ]
            message_en = "Core fixture data is ready; deterministic scenarios are blocked."
            message_th = "ข้อมูลหลักพร้อมใช้ แต่สถานการณ์จำลองยังถูกบล็อก"
        else:
            data_state = DataState.READY
            assumptions = [
                "Fixture values are synthetic and demonstrate the tested decision workflow.",
                "No road closure, shelter capacity, or evacuation condition is confirmed.",
            ]
            message_en = "Planning fixture demonstration; not an official warning."
            message_th = "ชุดข้อมูลสาธิตเพื่อการวางแผน ไม่ใช่ประกาศเตือนภัยอย่างเป็นทางการ"
        return StatusResponse(
            **self._common_fixture(
                source_name="FloodGuard committed synthetic artifacts",
                assumptions=assumptions,
                confidence_class="medium" if not decision_blocker else "low",
            ),
            study_area="fixture_thailand_demo",
            data_state=data_state,
            message_th=message_th,
            message_en=message_en,
        )

    def study_areas(self) -> list[StudyArea]:
        status = self.status()
        decision_artifacts_ready = status.data_state is not DataState.UNAVAILABLE
        area_count = len(self._priority()) if decision_artifacts_ready else 0
        return [
            StudyArea(
                **self._common_fixture(
                    source_name="sample_priority_scores.csv",
                    assumptions=[
                        "Small synthetic Thailand geometries are used for reproducible judging."
                    ],
                    confidence_class="medium" if area_count else "low",
                ),
                study_area_id="fixture_thailand_demo",
                title_th="พื้นที่สาธิต FloodGuard ประเทศไทย",
                title_en="FloodGuard Thailand fixture demonstration",
                area_count=area_count,
                data_state=status.data_state,
            )
        ]

    def areas(self, study_area: str = "fixture_thailand_demo") -> list[AreaDecision]:
        self._require_fixture_study_area(study_area)
        self._require_decision_artifacts()
        priority = self._priority()
        inputs = self._population_inputs()
        access = self._access_loss().set_index("subdistrict_id")
        equity = self._equity_gap().set_index("subdistrict_id")
        roads = self._road_risk()
        bridges = self._bridge_counts()
        facility_count = len(self._facilities())

        merged = priority.merge(
            inputs,
            on=[
                "subdistrict_id",
                "subdistrict_name",
                "confidence_class",
                "source_name",
                "source_timestamp",
                "assumptions",
            ],
            how="left",
            validate="one_to_one",
        )
        records: list[AreaDecision] = []
        for row in merged.to_dict(orient="records"):
            area_id = str(row["subdistrict_id"])
            area_roads = roads[roads["subdistrict_id"].astype(str) == area_id]
            equity_value = _optional_float(equity.loc[area_id, "equity_gap_ratio"])
            assumptions = _unique_strings(
                [
                    row["assumptions"],
                    "Access is nearest-facility shortest-path threshold analysis, not 2SFCA.",
                    (
                        "Road disruption probabilities are modelled fixture values, "
                        "not observed closures."
                    ),
                ]
            )
            records.append(
                AreaDecision(
                    **self._common_fixture(
                        source_name=str(row["source_name"]),
                        assumptions=assumptions,
                        confidence_class=str(row["confidence_class"]),
                    ),
                    area_id=area_id,
                    area_name_th=_THAI_AREA_NAMES.get(area_id, str(row["subdistrict_name"])),
                    area_name_en=str(row["subdistrict_name"]),
                    fpps_0_100=float(row["fpps_0_100"]),
                    action_class=str(row["action_class"]),
                    top_reason=str(row["top_reason"]),
                    flood_likelihood_0_100=float(row["flood_likelihood_0_100"]),
                    exposure_0_100=float(row["exposure_0_100"]),
                    access_gap_0_100=float(row["access_gap_0_100"]),
                    road_criticality_0_100=float(row["road_criticality_0_100"]),
                    vulnerability_context_0_100=float(row["vulnerability_context_0_100"]),
                    people_losing_30_min_access=_whole_number(
                        access.loc[area_id, "people_losing_30_min_access"]
                    ),
                    equity_gap_ratio=equity_value,
                    road_evidence=RoadEvidence(
                        at_risk_segments=len(area_roads),
                        bridge_count=bridges.get(area_id, 0),
                        summary=(
                            "Modelled fixture road-risk evidence; field verification is required."
                        ),
                    ),
                    facility_evidence=FacilityEvidence(
                        facility_count=facility_count,
                        summary=(
                            "One shared synthetic facility supports the deterministic "
                            "access fixture; capacity is not modelled."
                        ),
                    ),
                )
            )
        return records

    def area(
        self,
        area_id: str,
        study_area: str = "fixture_thailand_demo",
    ) -> AreaDecision:
        self._require_fixture_study_area(study_area)
        for area in self.areas(study_area):
            if area.area_id == area_id:
                return area
        raise ArtifactNotFound(f"Unknown area_id: {area_id}")

    def layers(self, study_area: str = "fixture_thailand_demo") -> list[LayerCatalogItem]:
        self._require_fixture_study_area(study_area)
        layer_specs = (
            {
                "layer_id": "priority_areas",
                "title_th": "พื้นที่จัดลำดับความสำคัญ",
                "title_en": "Priority areas",
                "roles": ["public", "command", "studio"],
                "file": self.paths.outputs / "priority_subdistricts.geojson",
                "assumptions": ["Synthetic WGS84 reporting polygons."],
                "required_properties": {"subdistrict_id"},
            },
            {
                "layer_id": "road_risk",
                "title_th": "ความเสี่ยงถนนเชิงแบบจำลอง",
                "title_en": "Modelled road risk",
                "roles": ["command", "studio"],
                "file": self.paths.outputs / "road_risk.geojson",
                "assumptions": ["Heuristic fixture road-risk values are not observed closures."],
                "required_properties": {"road_id", "subdistrict_id"},
            },
        )
        result: list[LayerCatalogItem] = []
        for spec in layer_specs:
            try:
                _read_geojson_artifact(
                    spec["file"],
                    required_properties=spec["required_properties"],
                )
            except ArtifactUnavailable:
                ready = False
            else:
                ready = True
            assumptions = list(spec["assumptions"])
            if not ready:
                assumptions.append("Layer artifact is missing or failed validation.")
            result.append(
                LayerCatalogItem(
                    **self._common_fixture(
                        source_name=spec["file"].name,
                        assumptions=assumptions,
                        confidence_class="medium" if ready else "low",
                    ),
                    layer_id=spec["layer_id"],
                    title_th=spec["title_th"],
                    title_en=spec["title_en"],
                    role_visibility=spec["roles"],
                    format="geojson",
                    url=f"/api/v1/layer-data/{spec['layer_id']}",
                    data_state="ready" if ready else "unavailable",
                    model_run_id=None,
                    attribution=["FloodGuard synthetic fixtures"],
                )
            )
        return result

    def layer_data(
        self,
        layer_id: str,
        study_area: str = "fixture_thailand_demo",
    ) -> dict[str, Any]:
        self._require_fixture_study_area(study_area)
        files = {
            "priority_areas": self.paths.outputs / "priority_subdistricts.geojson",
            "road_risk": self.paths.outputs / "road_risk.geojson",
        }
        path = files.get(layer_id)
        if path is None:
            raise ArtifactNotFound("Unknown layer_id.")
        required_properties = (
            {"subdistrict_id"} if layer_id == "priority_areas" else {"road_id", "subdistrict_id"}
        )
        payload = _read_geojson_artifact(
            path,
            required_properties=required_properties,
        )
        for feature in payload["features"]:
            properties = feature["properties"]
            subdistrict_id = properties.get("subdistrict_id")
            if "area_id" not in properties and subdistrict_id is not None:
                properties["area_id"] = str(subdistrict_id)
        return payload

    def layer_artifact_sha256(
        self,
        layer_id: str,
        study_area: str = "fixture_thailand_demo",
    ) -> str:
        """Return the immutable source-artifact checksum for an advertised layer."""

        self._require_fixture_study_area(study_area)
        files = {
            "priority_areas": self.paths.outputs / "priority_subdistricts.geojson",
            "road_risk": self.paths.outputs / "road_risk.geojson",
        }
        path = files.get(layer_id)
        if path is None:
            raise ArtifactNotFound("Unknown layer_id.")
        if not path.is_file():
            raise ArtifactUnavailable(f"GeoJSON artifact unavailable: {path.name}.")
        return _sha256(path)

    def brief(
        self,
        area_id: str,
        study_area: str = "fixture_thailand_demo",
    ) -> BriefResponse:
        self._require_fixture_study_area(study_area)
        area = self.area(area_id, study_area)
        path = self.paths.outputs / f"action_brief_{area_id}.md"
        if path.is_file():
            content = _read_markdown_artifact(path)
            source_name = path.name
        else:
            content = build_action_brief(
                self._priority(),
                self._road_risk(),
                self._access_loss(),
                self._equity_gap(),
                subdistrict_id=area_id,
            )
            source_name = "floodguard.briefs.build_action_brief"
        return BriefResponse(
            **self._common_fixture(
                source_name=source_name,
                assumptions=[
                    *area.assumptions,
                    "Bilingual planning brief; this is not an official warning.",
                ],
                confidence_class=area.confidence_class.value,
            ),
            area_id=area_id,
            file_name=f"action_brief_{area_id}.md",
            bilingual=True,
            media_type="text/markdown; charset=utf-8",
            content_markdown=content,
        )

    def run_scenario(self, request: ScenarioRunRequest) -> ScenarioRunResponse:
        self._require_fixture_study_area(request.study_area)
        scenario_blocker = self._scenario_artifact_blocker()
        if scenario_blocker:
            raise ArtifactUnavailable(scenario_blocker)
        try:
            population = _read_csv_artifact(
                self.paths.fixtures / "sample_population_nodes.csv",
                _SCENARIO_POPULATION_COLUMNS,
            )
            edges = _read_csv_artifact(
                self.paths.fixtures / "sample_access_edges.csv",
                _SCENARIO_EDGE_COLUMNS,
            )
            facilities = self._facilities()
            baseline_access = calculate_access_loss(population, edges, facilities)
            baseline_equity = compute_equity_gap(
                equity_input_from_access_loss(baseline_access, threshold=30)
            )
        except (KeyError, OSError, TypeError, ValueError) as exc:
            raise ArtifactUnavailable(
                "Scenario fixture artifacts are unreadable or fail the access contract."
            ) from exc

        if request.scenario_id == "add_temporary_shelter":
            kwargs: dict[str, Any] = {
                "node_id": request.parameters["node_id"],
                "capacity": request.parameters["capacity"],
            }
        else:
            kwargs = {"from_node": "P2B", "to_node": "F1"}
        scenario = run_access_scenario(
            population,
            edges,
            facilities,
            request.scenario_id,
            baseline_access=baseline_access,
            baseline_equity=baseline_equity,
            **kwargs,
        )

        baseline_access_index = baseline_access.set_index("subdistrict_id")
        baseline_equity_index = baseline_equity.set_index("subdistrict_id")
        scenario_access_index = scenario["access_loss"].set_index("subdistrict_id")
        scenario_equity_index = scenario["equity_gap"].set_index("subdistrict_id")
        results: list[ScenarioAreaResult] = []
        for area_id in baseline_access_index.index.astype(str):
            baseline_people = _whole_number(
                baseline_access_index.loc[area_id, "people_losing_30_min_access"]
            )
            scenario_people = _whole_number(
                scenario_access_index.loc[area_id, "people_losing_30_min_access"]
            )
            baseline_ratio = _optional_float(baseline_equity_index.loc[area_id, "equity_gap_ratio"])
            scenario_ratio = _optional_float(scenario_equity_index.loc[area_id, "equity_gap_ratio"])
            results.append(
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
            "Open synthetic fixtures drive the deterministic scenario engine.",
            "Access uses nearest-facility shortest-path thresholds, not 2SFCA.",
            (
                "FPPS is not recalculated because the tested scenario engine returns "
                "access and equity only."
            ),
        ]
        if request.scenario_id == "add_temporary_shelter":
            assumptions.append(
                "Shelter capacity is bounded planning metadata; the current access "
                "engine does not model capacity."
            )
        else:
            assumptions.append(
                "Road FG-RD-002 maps to the fixed P2B-F1 fixture edge; this is not "
                "an observed closure."
            )
        return ScenarioRunResponse(
            **self._common_fixture(
                source_name="floodguard.scenarios.run_access_scenario",
                assumptions=assumptions,
                confidence_class="medium",
            ),
            run_id=run_id_for(request),
            scenario_id=request.scenario_id,
            study_area=request.study_area,
            parameters=request.parameters,
            run_status="completed",
            result_state="ready",
            backend_config_version=BACKEND_CONFIG_VERSION,
            access_method=ACCESS_METHOD,
            fpps_recalculated=False,
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
                baseline_max_equity_gap_ratio=_optional_float(
                    summary["baseline_max_equity_gap_ratio"]
                ),
                scenario_max_equity_gap_ratio=_optional_float(
                    summary["scenario_max_equity_gap_ratio"]
                ),
                change_max_equity_gap_ratio=_optional_float(summary["change_max_equity_gap_ratio"]),
            ),
            areas=results,
        )

    def model_runs(self) -> list[ModelRun]:
        return [self._synthetic_baseline_run(), self._weak_label_run()]

    def model_run(self, run_id: str) -> ModelRun:
        for run in self.model_runs():
            if run.run_id == run_id:
                return run
        raise ArtifactNotFound(f"Unknown model run_id: {run_id}")

    def readiness(self) -> list[ReadinessItem]:
        path = self.paths.outputs / "label_factory_readiness.csv"
        try:
            frame = _read_csv_artifact(path, _READINESS_COLUMNS)
        except ArtifactUnavailable:
            return [
                ReadinessItem(
                    check_id="label_factory_readiness_artifact",
                    phase="service",
                    status="unavailable",
                    source_status="unavailable",
                    severity="critical",
                    observed="The committed readiness table is unavailable.",
                    required="A validated, committed label-factory readiness table.",
                    reason_blocked="Readiness cannot be inferred from missing evidence.",
                    source_timestamp=WEAK_SOURCE_TIMESTAMP,
                    confidence_class="low",
                    assumptions=["Missing evidence remains blocked rather than inferred."],
                )
            ]
        rows: list[ReadinessItem] = []
        try:
            for row in frame.to_dict(orient="records"):
                source_status = _text(row.get("status"), "unavailable")
                status = "ready" if source_status == "ready" else "blocked"
                reason = _text(row.get("blocker"), "")
                if status == "blocked" and not reason:
                    reason = "Source status is not fully ready for production use."
                rows.append(
                    ReadinessItem(
                        check_id=_text(row.get("check_id"), "unknown_check"),
                        phase=_text(row.get("phase"), "unknown_phase"),
                        status=status,
                        source_status=source_status,
                        severity=_text(row.get("severity"), "critical"),
                        observed=_text(row.get("observed"), "Not reported."),
                        required=_text(row.get("required"), "Required evidence not reported."),
                        reason_blocked=reason,
                        source_timestamp=pd.to_datetime(
                            row.get("source_timestamp"),
                            utc=True,
                        ).to_pydatetime(),
                        confidence_class=_text(row.get("confidence_class"), "low"),
                        assumptions=[
                            _text(
                                row.get("assumptions"),
                                "Missing evidence remains blocked rather than inferred.",
                            )
                        ],
                    )
                )
        except (KeyError, TypeError, ValueError) as exc:
            raise ArtifactUnavailable("Readiness artifact failed typed row validation.") from exc
        return rows

    def _synthetic_baseline_run(self) -> ModelRun:
        metrics_path = self.paths.outputs / "sample_sar_validation_metrics.csv"
        probabilities_path = self.paths.outputs / "sample_sar_baseline.csv"
        input_path = self.paths.fixtures / "sample_sar_pixels.csv"
        metrics = _read_csv_artifact(metrics_path, _SYNTHETIC_METRIC_COLUMNS).iloc[0]
        probabilities = _read_csv_artifact(
            probabilities_path,
            _SYNTHETIC_PROBABILITY_COLUMNS,
        )
        _read_csv_artifact(input_path, _SYNTHETIC_INPUT_COLUMNS)
        brier = float(
            (
                (
                    probabilities["flood_probability_0_1"].astype(float)
                    - probabilities["reference_flood_extent"].astype(float)
                )
                ** 2
            ).mean()
        )
        return ModelRun(
            **self._common_fixture(
                source_name=metrics_path.name,
                assumptions=[
                    "Tiny synthetic threshold fixture only; no real Sentinel-1 accuracy claim."
                ],
                confidence_class="low",
            ),
            run_id="synthetic-sar-baseline-v1",
            study_area="fixture_thailand_demo",
            model_family="deterministic_sar_baseline",
            run_status="completed",
            geoai_version=None,
            geoai_commit=None,
            model_id="legacy_synthetic_sar_v1",
            model_revision="1",
            model_sha256=None,
            architecture="deterministic_threshold",
            encoder=None,
            encoder_weights=None,
            num_channels=4,
            channel_names=["pre_vv_db", "post_vv_db", "pre_vh_db", "post_vh_db"],
            preprocessing={
                "method": "Versioned physical dB-change formula; no implicit /255 transform.",
                "value_domain": "physical_units",
                "sidecar_sha256": None,
                "transforms": [],
            },
            input_manifest_rows=[
                {
                    "product_id": "sample_sar_pixels_v1",
                    "role": "synthetic_fixture_table",
                    "sha256": _sha256(input_path),
                    "source_timestamp": FIXTURE_SOURCE_TIMESTAMP,
                    "processing_allowed": True,
                }
            ],
            encoded_feature_sha256=None,
            reference_mask_sha256=None,
            prepared_tile_manifest_sha256=None,
            spatial_holdout_ids=[],
            spatial_partitions=[],
            reference_mask_id="sample_sar_pixels_reference_extent_v1",
            reference_mask_status="synthetic_fixture",
            target_crs="fixture_row_col_grid",
            resolution=(1.0, 1.0),
            bounds=(0.0, 0.0, 3.0, 2.0),
            tile_size=3,
            overlap=0,
            stride=3,
            batch_size=1,
            device="cpu",
            flood_class_index=1,
            probability_threshold=0.5,
            external_output_workspace="temporary-test-workspace",
            processing_scope="synthetic_threshold_contract_test_only",
            processing_allowed=True,
            can_feed_decision_layer=False,
            reason_blocked="Synthetic fixture only; not evidence for a real decision layer.",
            validation_metrics={
                "iou": float(metrics["iou"]),
                "f1_dice": float(metrics["f1_dice"]),
                "precision": float(metrics["precision"]),
                "recall": float(metrics["recall"]),
                "area_error_ratio": abs(float(metrics["area_error_ratio"])),
                "brier_score": brier,
            },
            error_categories=["synthetic_fixture_only"],
        )

    def _weak_label_run(self) -> ModelRun:
        metrics_path = self.paths.outputs / "mae_sai_weak_label_ml_metrics.csv"
        features_path = self.paths.outputs / "mae_sai_weak_sar_feature_manifest.csv"
        acquisition_path = self.paths.outputs / "cdse_mae_sai_acquisition_manifest.csv"
        reference_path = self.paths.outputs / "manual_reference_mask_manifest.csv"
        metrics = _read_csv_artifact(metrics_path, _WEAK_METRIC_COLUMNS).iloc[0]
        features = _read_csv_artifact(features_path, _WEAK_FEATURE_COLUMNS).iloc[0]
        acquisitions = _read_csv_artifact(
            acquisition_path,
            _ACQUISITION_COLUMNS,
        ).set_index("product_id")
        reference = _read_csv_artifact(reference_path, _REFERENCE_COLUMNS).iloc[0]
        manifest_rows: list[dict[str, Any]] = []
        for role in ("pre", "post"):
            product_id = str(features[f"{role}_product_id"])
            row = acquisitions.loc[product_id]
            manifest_rows.append(
                {
                    "product_id": product_id,
                    "role": f"{role}_event_sar",
                    "sha256": str(row["sha256"]),
                    "source_timestamp": pd.to_datetime(
                        row["acquisition_date"],
                        utc=True,
                    ).to_pydatetime(),
                    "processing_allowed": False,
                }
            )
        manifest_rows.append(
            {
                "product_id": str(reference["reference_id"]),
                "role": "reference_mask",
                "sha256": str(reference["sha256"]),
                "source_timestamp": WEAK_SOURCE_TIMESTAMP,
                "processing_allowed": False,
            }
        )
        width = int(features["sample_width"])
        height = int(features["sample_height"])
        lon_span = float(features["bbox_lon_max"]) - float(features["bbox_lon_min"])
        lat_span = float(features["bbox_lat_max"]) - float(features["bbox_lat_min"])
        return ModelRun(
            schema_version="1.0",
            dataset_mode="candidate",
            operational_status="non_operational",
            source_timestamp=WEAK_SOURCE_TIMESTAMP,
            generated_at=self.generated_at,
            confidence_class="low",
            source_name=metrics_path.name,
            assumptions=[
                "Spatial holdout against a manually digitized weak-reference mask.",
                "Metric improvement cannot override the safety boundary.",
            ],
            official_warning=False,
            data_version="mae-sai-weak-label-v1",
            git_commit=DATA_GIT_COMMIT,
            run_id="mae-sai-weak-label-logistic-v1",
            study_area="mae_sai_2024",
            model_family="weak_label_logistic",
            run_status="completed",
            geoai_version=None,
            geoai_commit=None,
            model_id=str(metrics["experiment_name"]),
            model_revision="1",
            model_sha256=None,
            architecture="weighted_logistic_regression",
            encoder=None,
            encoder_weights=None,
            num_channels=len(str(metrics["feature_columns"]).split("|")),
            channel_names=str(metrics["feature_columns"]).split("|"),
            preprocessing={
                "method": "Training-partition standardization with spatial-block holdout.",
                "value_domain": "physical_units",
                "sidecar_sha256": None,
                "transforms": [],
            },
            input_manifest_rows=manifest_rows,
            encoded_feature_sha256=None,
            reference_mask_sha256=str(reference["sha256"]),
            prepared_tile_manifest_sha256=None,
            spatial_holdout_ids=["mae-sai-spatial-block-holdout"],
            spatial_partitions=[],
            reference_mask_id=str(features["reference_product_id"]),
            reference_mask_status=str(features["reference_status"]),
            target_crs="EPSG:4326",
            resolution=(lon_span / width, lat_span / height),
            bounds=(
                float(features["bbox_lon_min"]),
                float(features["bbox_lat_min"]),
                float(features["bbox_lon_max"]),
                float(features["bbox_lat_max"]),
            ),
            tile_size=256,
            overlap=0,
            stride=256,
            batch_size=1,
            device="cpu",
            flood_class_index=1,
            probability_threshold=float(metrics["decision_threshold"]),
            external_output_workspace="external-data-workspace/mae-sai-weak-label-v1",
            processing_scope="weak_label_candidate_metrics_only",
            processing_allowed=False,
            can_feed_decision_layer=False,
            reason_blocked="Weak labels are not official truth or field validation.",
            validation_metrics={
                "iou": float(metrics["ml_iou"]),
                "f1_dice": float(metrics["ml_f1_dice"]),
                "precision": float(metrics["ml_precision"]),
                "recall": float(metrics["ml_recall"]),
                "area_error_ratio": abs(float(metrics["ml_area_error_ratio"])),
                "brier_score": None,
            },
            error_categories=["weak_reference_only", "area_overprediction"],
        )

    def _common_fixture(
        self,
        *,
        source_name: str,
        assumptions: list[str],
        confidence_class: str,
    ) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "dataset_mode": "fixture_demo",
            "operational_status": "non_operational",
            "source_timestamp": FIXTURE_SOURCE_TIMESTAMP,
            "generated_at": self.generated_at,
            "confidence_class": confidence_class,
            "source_name": source_name,
            "assumptions": _unique_strings(assumptions),
            "official_warning": False,
            "data_version": FIXTURE_DATA_VERSION,
            "git_commit": DATA_GIT_COMMIT,
        }

    def _decision_artifact_blocker(self) -> str | None:
        """Return a sanitized blocker if core decision artifacts are not coherent."""

        try:
            priority = self._priority_frame
            population = self._population_frame
            access = self._access_frame
            equity = self._equity_frame
            roads = self._road_frame
            facilities = self._facility_frame
            _read_geojson_artifact(
                self.paths.outputs / "priority_subdistricts.geojson",
                required_properties={"subdistrict_id"},
            )

            priority_ids = _validated_id_set(
                priority,
                "subdistrict_id",
                "sample_priority_scores.csv",
            )
            for frame, name in (
                (population, "sample_population.csv"),
                (access, "sample_access_loss.csv"),
                (equity, "sample_equity_gap.csv"),
            ):
                if _validated_id_set(frame, "subdistrict_id", name) != priority_ids:
                    raise ArtifactUnavailable(
                        f"{name} reporting-unit IDs do not match the priority artifact."
                    )
            road_ids = _validated_id_set(
                roads,
                "subdistrict_id",
                "sample_road_risk.csv",
                require_unique=False,
            )
            if not road_ids.issubset(priority_ids):
                raise ArtifactUnavailable(
                    "sample_road_risk.csv contains an unknown reporting-unit ID."
                )
            _validated_id_set(
                facilities,
                "facility_id",
                "sample_facilities.csv",
            )
            _validate_numeric_range(
                priority,
                "fpps_0_100",
                minimum=0,
                maximum=100,
                artifact_name="sample_priority_scores.csv",
            )
            if not set(priority["action_class"].astype(str)).issubset({"A", "B", "C", "D", "E"}):
                raise ArtifactUnavailable(
                    "sample_priority_scores.csv contains an invalid action class."
                )
            for column in (
                "flood_likelihood_0_100",
                "exposure_0_100",
                "access_gap_0_100",
                "road_criticality_0_100",
                "vulnerability_context_0_100",
            ):
                _validate_numeric_range(
                    population,
                    column,
                    minimum=0,
                    maximum=100,
                    artifact_name="sample_population.csv",
                )
            _validate_numeric_range(
                access,
                "people_losing_30_min_access",
                minimum=0,
                artifact_name="sample_access_loss.csv",
            )
        except ArtifactUnavailable as exc:
            return str(exc)
        except (KeyError, TypeError, ValueError):
            return "Decision artifacts failed consistency validation."
        return None

    def _scenario_artifact_blocker(self) -> str | None:
        """Return a sanitized blocker for deterministic scenario inputs."""

        try:
            population = _read_csv_artifact(
                self.paths.fixtures / "sample_population_nodes.csv",
                _SCENARIO_POPULATION_COLUMNS,
            )
            edges = _read_csv_artifact(
                self.paths.fixtures / "sample_access_edges.csv",
                _SCENARIO_EDGE_COLUMNS,
            )
            facilities = self._facility_frame
            _validated_id_set(
                population,
                "node_id",
                "sample_population_nodes.csv",
            )
            _validated_id_set(
                facilities,
                "facility_id",
                "sample_facilities.csv",
            )
            if edges[["from_node", "to_node"]].isna().any().any():
                raise ArtifactUnavailable("sample_access_edges.csv contains an empty endpoint.")
            for column in ("normal_minutes", "disrupted_minutes"):
                _validate_numeric_range(
                    edges,
                    column,
                    minimum=0,
                    artifact_name="sample_access_edges.csv",
                    allow_missing=column == "disrupted_minutes",
                )
        except ArtifactUnavailable as exc:
            detail = str(exc)
            if detail.startswith("Scenario fixture artifacts unavailable:"):
                return detail
            return "Scenario fixture artifacts unavailable or invalid: " + detail
        except (KeyError, TypeError, ValueError):
            return "Scenario fixture artifacts unavailable or failed consistency validation."
        return None

    def _require_decision_artifacts(self) -> None:
        blocker = self._decision_artifact_blocker()
        if blocker:
            raise ArtifactUnavailable(blocker)

    @cached_property
    def _priority_frame(self) -> pd.DataFrame:
        return _read_csv_artifact(
            self.paths.outputs / "sample_priority_scores.csv",
            _PRIORITY_COLUMNS,
        )

    def _priority(self) -> pd.DataFrame:
        return self._priority_frame.copy()

    @cached_property
    def _population_frame(self) -> pd.DataFrame:
        return _read_csv_artifact(
            self.paths.fixtures / "sample_population.csv",
            _POPULATION_INPUT_COLUMNS,
        )

    def _population_inputs(self) -> pd.DataFrame:
        return self._population_frame.copy()

    @cached_property
    def _access_frame(self) -> pd.DataFrame:
        return _read_csv_artifact(
            self.paths.outputs / "sample_access_loss.csv",
            _ACCESS_COLUMNS,
        )

    def _access_loss(self) -> pd.DataFrame:
        return self._access_frame.copy()

    @cached_property
    def _equity_frame(self) -> pd.DataFrame:
        return _read_csv_artifact(
            self.paths.outputs / "sample_equity_gap.csv",
            _EQUITY_COLUMNS,
        )

    def _equity_gap(self) -> pd.DataFrame:
        return self._equity_frame.copy()

    @cached_property
    def _road_frame(self) -> pd.DataFrame:
        return _read_csv_artifact(
            self.paths.outputs / "sample_road_risk.csv",
            _ROAD_RISK_COLUMNS,
        )

    def _road_risk(self) -> pd.DataFrame:
        return self._road_frame.copy()

    @cached_property
    def _facility_frame(self) -> pd.DataFrame:
        return _read_csv_artifact(
            self.paths.fixtures / "sample_facilities.csv",
            _FACILITY_COLUMNS,
        )

    def _facilities(self) -> pd.DataFrame:
        return self._facility_frame.copy()

    @cached_property
    def _bridge_count_map(self) -> dict[str, int]:
        path = self.paths.fixtures / "sample_roads.geojson"
        if not path.is_file():
            return {}
        collection = _read_geojson_artifact(
            path,
            required_properties={"subdistrict_id", "bridge_flag"},
        )
        counts: dict[str, int] = {}
        for feature in collection.get("features", []):
            properties = feature.get("properties", {})
            if properties.get("bridge_flag") is True:
                area_id = str(properties.get("subdistrict_id", ""))
                counts[area_id] = counts.get(area_id, 0) + 1
        return counts

    def _bridge_counts(self) -> dict[str, int]:
        return dict(self._bridge_count_map)


def _read_csv_artifact(
    path: Path,
    required_columns: frozenset[str],
) -> pd.DataFrame:
    """Read a small CSV artifact and fail with a path-safe contract error."""

    if not path.is_file():
        raise ArtifactUnavailable(f"Artifact unavailable: {path.name}.")
    try:
        frame = pd.read_csv(path)
    except (OSError, UnicodeError, pd.errors.ParserError) as exc:
        raise ArtifactUnavailable(f"Artifact is not readable CSV: {path.name}.") from exc
    missing = sorted(required_columns.difference(frame.columns))
    if missing:
        raise ArtifactUnavailable(
            f"Artifact {path.name} is missing required columns: {', '.join(missing)}."
        )
    if frame.empty:
        raise ArtifactUnavailable(f"Artifact contains no rows: {path.name}.")
    return frame


def _read_geojson_artifact(
    path: Path,
    *,
    required_properties: set[str],
) -> dict[str, Any]:
    """Read a committed GeoJSON FeatureCollection with structural checks."""

    if not path.is_file():
        raise ArtifactUnavailable(f"GeoJSON artifact unavailable: {path.name}.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ArtifactUnavailable(f"GeoJSON artifact is unreadable: {path.name}.") from exc
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise ArtifactUnavailable(f"GeoJSON artifact is not a FeatureCollection: {path.name}.")
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        raise ArtifactUnavailable(f"GeoJSON artifact has no features: {path.name}.")
    for index, feature in enumerate(features):
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ArtifactUnavailable(
                f"GeoJSON artifact {path.name} has an invalid feature at index {index}."
            )
        properties = feature.get("properties")
        geometry = feature.get("geometry")
        if not isinstance(properties, dict) or not isinstance(geometry, dict):
            raise ArtifactUnavailable(
                f"GeoJSON artifact {path.name} has an incomplete feature at index {index}."
            )
        missing = sorted(required_properties.difference(properties))
        if missing:
            raise ArtifactUnavailable(
                f"GeoJSON artifact {path.name} feature {index} is missing properties: "
                + ", ".join(missing)
                + "."
            )
        if not isinstance(geometry.get("type"), str) or "coordinates" not in geometry:
            raise ArtifactUnavailable(
                f"GeoJSON artifact {path.name} has invalid geometry at index {index}."
            )
    return payload


def _read_markdown_artifact(path: Path) -> str:
    """Read a non-empty UTF-8 Markdown artifact without leaking its local path."""

    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ArtifactUnavailable(f"Markdown artifact is unreadable: {path.name}.") from exc
    if not content.strip() or not content.lstrip().startswith("#"):
        raise ArtifactUnavailable(f"Markdown artifact is invalid: {path.name}.")
    return content


def _validated_id_set(
    frame: pd.DataFrame,
    column: str,
    artifact_name: str,
    *,
    require_unique: bool = True,
) -> set[str]:
    values = frame[column]
    if values.isna().any() or (values.astype(str).str.strip() == "").any():
        raise ArtifactUnavailable(f"{artifact_name} contains an empty {column}.")
    normalized = values.astype(str)
    if require_unique and normalized.duplicated().any():
        raise ArtifactUnavailable(f"{artifact_name} contains duplicate {column} values.")
    return set(normalized)


def _validate_numeric_range(
    frame: pd.DataFrame,
    column: str,
    *,
    minimum: float,
    artifact_name: str,
    maximum: float | None = None,
    allow_missing: bool = False,
) -> None:
    try:
        values = pd.to_numeric(frame[column], errors="raise").astype(float)
    except (KeyError, TypeError, ValueError) as exc:
        raise ArtifactUnavailable(f"{artifact_name} contains a non-numeric {column}.") from exc
    valid_values = values.dropna() if allow_missing else values
    if (not allow_missing and values.isna().any()) or not valid_values.map(math.isfinite).all():
        raise ArtifactUnavailable(f"{artifact_name} contains an invalid {column}.")
    if (valid_values < minimum).any() or (maximum is not None and (valid_values > maximum).any()):
        raise ArtifactUnavailable(f"{artifact_name} contains an out-of-range {column}.")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _whole_number(value: Any) -> int:
    return int(round(float(value)))


def _optional_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    result = float(value)
    if not math.isfinite(result):
        return None
    return result


def _optional_delta(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None:
        return None
    return value - baseline


def _text(value: Any, fallback: str) -> str:
    if value is None or pd.isna(value):
        return fallback
    text = str(value).strip()
    return text or fallback


def _unique_strings(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = _text(value, "")
        if text and text not in result:
            result.append(text)
    return result
