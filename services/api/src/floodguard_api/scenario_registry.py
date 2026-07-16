"""Closed scenario registry and deterministic parameter normalization."""

from __future__ import annotations

import re

from floodguard_api.models import ScenarioDefinition, ScenarioRunRequest

BACKEND_CONFIG_VERSION = "fixture-access-scenarios-v1"
ACCESS_METHOD = "nearest_facility_shortest_path_threshold"


def definitions() -> list[ScenarioDefinition]:
    """Return the complete, server-owned scenario registry."""

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

    if request.scenario_id == "add_temporary_shelter":
        return f"fixture-add-temporary-shelter-p2a-capacity-{request.parameters['capacity']}-v1"
    return "fixture-close-road-fg-rd-002-v1"


def request_from_run_id(run_id: str) -> ScenarioRunRequest | None:
    """Recover a validated request so GET remains stateless across restarts."""

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
