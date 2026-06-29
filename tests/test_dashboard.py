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
        [
            OUTPUTS / "action_brief_FG-TB-001.md",
            OUTPUTS / "action_brief_FG-TB-002.md",
            OUTPUTS / "action_brief_FG-TB-003.md",
        ],
        output_path,
    )

    html = output_path.read_text(encoding="utf-8")
    assert written == output_path
    assert "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" in html
    assert "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" in html
    assert "const priorityData =" in html
    assert "const roadRiskData =" in html
    assert "const briefsBySubdistrict =" in html
    assert 'id="subdistrict-select"' in html
    assert 'id="scenario-select"' in html
    assert 'class="action-filter"' in html
    assert "temporary shelter delta" in html
    assert "road closure delta" in html
    assert "Best intervention effect" in html
    assert "Worst road-closure stress case" in html
    assert "Temporary shelter: -30 people losing 30-min access" in html
    assert "Road closure: +50 people losing 30-min access" in html
    assert 'id="download-current-brief"' in html
    assert 'id="download-filtered-geojson"' in html
    assert "Download current brief" in html
    assert "Download filtered GeoJSON" in html
    assert "function downloadCurrentActionBrief" in html
    assert "function downloadFilteredGeoJSON" in html
    assert "function downloadText" in html
    assert "new Blob" in html
    assert "priority_subdistricts_filtered.geojson" in html
    assert "Delta improves" in html
    assert "Delta worsens" in html
    assert "Action Brief" in html
    assert "Validation Summary" in html
    assert "A Protect Lives" in html
    assert "action_brief_FG-TB-001" not in html
    assert "FG-TB-001" in html
    assert "FG-TB-002" in html
    assert "FG-TB-003" in html
    assert "temporary_shelter_change_people_losing_30_min_access" in html
    assert "road_closure_change_people_losing_30_min_access" in html
    assert "function selectSubdistrict" in html
    assert "function renderPriorityLayer" in html
    assert "fetch(" not in html


def test_dashboard_output_contract_path() -> None:
    assert (OUTPUTS / "dashboard.html").as_posix().endswith("outputs/dashboard.html")
