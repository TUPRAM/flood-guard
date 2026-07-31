"""Closed scenario registry and deterministic parameter normalization."""

from __future__ import annotations

import re

from floodguard_api.models import ScenarioDefinition, ScenarioRunRequest

BACKEND_CONFIG_VERSION = "fixture-access-scenarios-v1"
MAE_SAI_BACKEND_CONFIG_VERSION = "mae-sai-candidate-access-scenarios-v1"
ACCESS_METHOD = "nearest_facility_shortest_path_threshold"
MAE_SAI_TEMPORARY_SHELTER_NODE = "N-99.9742609-20.4457677"
MAE_SAI_CLOSE_EDGE_ID = "MS-EDGE-0008687"
MAE_SAI_CLOSE_RUN_ID = "mae-sai-candidate-close-edge-ms-edge-0008687-v1"


def definitions(study_area: str = "fixture_thailand_demo") -> list[ScenarioDefinition]:
    """Return the complete, server-owned scenario registry."""

    if study_area == "mae_sai_candidate_v1":
        return _mae_sai_definitions()
    if study_area != "fixture_thailand_demo":
        return []

    return [
        ScenarioDefinition(
            scenario_id="add_temporary_shelter",
            title_th="เพิ่มจุดพักพิงชั่วคราวเพื่อซ้อมแผน",
            title_en="Add a temporary shelter for planning rehearsal",
            description_th=("คำนวณการเข้าถึงสถานบริการที่ใกล้ที่สุดใหม่จากข้อมูลสาธิต ไม่ใช่เส้นทางอพยพแบบสด"),
            description_en=(
                "Recomputes nearest-facility access on fixtures; this is not a live "
                "evacuation route."
            ),
            parameters=[
                {
                    "name": "node_id",
                    "value_type": "string",
                    "required": False,
                    "default": "P2A",
                    "allowed_values": ["P2A"],
                    "note": "Only the fixture node approved by the service registry.",
                },
                {
                    "name": "capacity",
                    "value_type": "integer",
                    "required": False,
                    "default": 500,
                    "minimum": 1,
                    "maximum": 5000,
                    "note": (
                        "Planning metadata only; the tested nearest-facility access "
                        "engine does not model shelter capacity."
                    ),
                },
            ],
            backend_config_version=BACKEND_CONFIG_VERSION,
            access_method=ACCESS_METHOD,
        ),
        ScenarioDefinition(
            scenario_id="close_road",
            title_th="ปิดถนนตัวอย่างเพื่อซ้อมแผน",
            title_en="Close one fixture road for planning rehearsal",
            description_th=("ตัดการเชื่อมต่อถนนตัวอย่างที่กำหนดโดยเซิร์ฟเวอร์และคำนวณการเข้าถึงใหม่"),
            description_en=("Disconnects one server-approved fixture edge and recomputes access."),
            parameters=[
                {
                    "name": "road_id",
                    "value_type": "string",
                    "required": False,
                    "default": "FG-RD-002",
                    "allowed_values": ["FG-RD-002"],
                    "note": "Only the fixture road approved by the service registry.",
                }
            ],
            backend_config_version=BACKEND_CONFIG_VERSION,
            access_method=ACCESS_METHOD,
        ),
    ]


def run_id_for(request: ScenarioRunRequest) -> str:
    """Encode all accepted parameters in a stable, restart-safe run ID."""

    if request.study_area == "mae_sai_candidate_v1":
        if request.scenario_id == "add_temporary_shelter":
            return (
                "mae-sai-candidate-add-temporary-shelter-"
                f"n-99-9742609-20-4457677-capacity-{request.parameters['capacity']}-v1"
            )
        return MAE_SAI_CLOSE_RUN_ID
    if request.scenario_id == "add_temporary_shelter":
        return f"fixture-add-temporary-shelter-p2a-capacity-{request.parameters['capacity']}-v1"
    return "fixture-close-road-fg-rd-002-v1"


def request_from_run_id(run_id: str) -> ScenarioRunRequest | None:
    """Recover a validated request so GET remains stateless across restarts."""

    candidate_shelter_match = re.fullmatch(
        r"mae-sai-candidate-add-temporary-shelter-"
        r"n-99-9742609-20-4457677-capacity-(\d+)-v1",
        run_id,
    )
    if candidate_shelter_match:
        try:
            return ScenarioRunRequest(
                scenario_id="add_temporary_shelter",
                study_area="mae_sai_candidate_v1",
                parameters={
                    "node_id": MAE_SAI_TEMPORARY_SHELTER_NODE,
                    "capacity": int(candidate_shelter_match.group(1)),
                },
            )
        except ValueError:
            return None
    if run_id == MAE_SAI_CLOSE_RUN_ID:
        return ScenarioRunRequest(
            scenario_id="close_road",
            study_area="mae_sai_candidate_v1",
            parameters={"edge_id": MAE_SAI_CLOSE_EDGE_ID},
        )

    shelter_match = re.fullmatch(
        r"fixture-add-temporary-shelter-p2a-capacity-(\d+)-v1",
        run_id,
    )
    if shelter_match:
        try:
            return ScenarioRunRequest(
                scenario_id="add_temporary_shelter",
                parameters={
                    "node_id": "P2A",
                    "capacity": int(shelter_match.group(1)),
                },
            )
        except ValueError:
            return None
    if run_id == "fixture-close-road-fg-rd-002-v1":
        return ScenarioRunRequest(
            scenario_id="close_road",
            parameters={"road_id": "FG-RD-002"},
        )
    return None


def _mae_sai_definitions() -> list[ScenarioDefinition]:
    """Return only scenarios bound to immutable Mae Sai graph identifiers."""

    return [
        ScenarioDefinition(
            scenario_id="add_temporary_shelter",
            title_th="เพิ่มจุดพักพิงชั่วคราวเพื่อซ้อมแผน",
            title_en="Add a temporary facility candidate for planning rehearsal",
            description_th=(
                "คำนวณการเข้าถึงสถานที่ใกล้ที่สุดใหม่บนกราฟผู้สมัครแม่สาย "
                "ไม่ใช่เส้นทางอพยพแบบสด"
            ),
            description_en=(
                "Recomputes nearest-facility access on the immutable Mae Sai candidate "
                "graph; this is not a live evacuation route."
            ),
            parameters=[
                {
                    "name": "node_id",
                    "value_type": "string",
                    "required": False,
                    "default": MAE_SAI_TEMPORARY_SHELTER_NODE,
                    "allowed_values": [MAE_SAI_TEMPORARY_SHELTER_NODE],
                    "note": "Only the graph node pinned by the server registry.",
                },
                {
                    "name": "capacity",
                    "value_type": "integer",
                    "required": False,
                    "default": 500,
                    "minimum": 1,
                    "maximum": 5000,
                    "note": (
                        "Planning metadata only; the nearest-facility engine does not "
                        "model capacity."
                    ),
                },
            ],
            backend_config_version=MAE_SAI_BACKEND_CONFIG_VERSION,
            access_method=ACCESS_METHOD,
        ),
        ScenarioDefinition(
            scenario_id="close_road",
            title_th="ปิดขอบกราฟผู้สมัครหนึ่งเส้นเพื่อซ้อมแผน",
            title_en="Close one candidate graph edge for planning rehearsal",
            description_th=(
                "ตัดขอบกราฟที่เซิร์ฟเวอร์กำหนดและคำนวณการเข้าถึงใหม่ "
                "ไม่ใช่รายงานถนนปิดจริง"
            ),
            description_en=(
                "Closes one server-pinned candidate graph edge and recomputes access; "
                "this is not an observed road closure."
            ),
            parameters=[
                {
                    "name": "edge_id",
                    "value_type": "string",
                    "required": False,
                    "default": MAE_SAI_CLOSE_EDGE_ID,
                    "allowed_values": [MAE_SAI_CLOSE_EDGE_ID],
                    "note": "Only the immutable graph edge pinned by the server registry.",
                }
            ],
            backend_config_version=MAE_SAI_BACKEND_CONFIG_VERSION,
            access_method=ACCESS_METHOD,
        ),
    ]
