from __future__ import annotations

from pathlib import Path

from floodguard.dashboard_smoke import (
    DashboardSmokeError,
    format_smoke_report,
    run_dashboard_smoke_checks,
    smoke_checks_passed,
)

OUTPUTS = Path(__file__).parents[1] / "outputs"


def test_dashboard_smoke_checks_current_output() -> None:
    checks = run_dashboard_smoke_checks(
        OUTPUTS / "dashboard.html",
        check_network_tiles=False,
    )

    assert smoke_checks_passed(checks)
    names = {check.name for check in checks}
    assert {
        "page_title",
        "local_static_server_fetch",
        "embedded_priority_geojson",
        "priority_polygon_renderer",
        "road_risk_renderer",
        "facility_cluster_renderer",
        "bilingual_interface",
        "sar_evidence_drawer",
        "modality_context_panel",
        "historical_susceptibility_context",
        "historical_context_boundary",
        "judge_presentation_mode",
        "label_overlap_guard",
        "validation_cards_visible",
        "brief_summary_visible",
        "export_current_brief",
        "export_filtered_geojson",
        "leaflet_tile_probe",
    }.issubset(names)


def test_dashboard_smoke_report_marks_failures(tmp_path: Path) -> None:
    broken = tmp_path / "dashboard.html"
    broken.write_text("<html><title>Broken</title></html>", encoding="utf-8")

    checks = run_dashboard_smoke_checks(broken, check_network_tiles=False)
    report = format_smoke_report(checks)

    assert not smoke_checks_passed(checks)
    assert "FAIL" in report
    assert "`page_title`" in report
    assert "`local_static_server_fetch`" in report


def test_dashboard_smoke_requires_dashboard_html(tmp_path: Path) -> None:
    wrong_name = tmp_path / "index.html"
    wrong_name.write_text("<html></html>", encoding="utf-8")

    try:
        run_dashboard_smoke_checks(wrong_name)
    except DashboardSmokeError as exc:
        assert "dashboard.html" in str(exc)
    else:
        raise AssertionError("Expected DashboardSmokeError.")
