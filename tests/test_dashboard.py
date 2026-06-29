from __future__ import annotations

from pathlib import Path

from floodguard.dashboard import write_static_dashboard

OUTPUTS = Path(__file__).parents[1] / "outputs"


def test_write_static_dashboard_embeds_outputs_without_backend_fetch(tmp_path: Path) -> None:
    output_path = tmp_path / "dashboard.html"

    written = write_static_dashboard(
        OUTPUTS / "priority_subdistricts.geojson",
        OUTPUTS / "road_risk.geojson",
        OUTPUTS / "validation_summary.md",
        OUTPUTS / "action_brief_FG-TB-001.md",
        output_path,
    )

    html = output_path.read_text(encoding="utf-8")
    assert written == output_path
    assert "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" in html
    assert "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" in html
    assert "const priorityData =" in html
    assert "const roadRiskData =" in html
    assert "Action Brief" in html
    assert "Validation Summary" in html
    assert "A Protect Lives" in html
    assert "temporary_shelter_change_people_losing_30_min_access" in html
    assert "road_closure_change_people_losing_30_min_access" in html
    assert "fetch(" not in html


def test_dashboard_output_contract_path() -> None:
    assert (OUTPUTS / "dashboard.html").as_posix().endswith("outputs/dashboard.html")
