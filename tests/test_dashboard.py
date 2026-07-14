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
        theos2_preview_manifest_path=OUTPUTS / "theos2_selected_file_manifest.csv",
    )

    html = output_path.read_text(encoding="utf-8")
    assert written == output_path
    assert "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" in html
    assert "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" in html
    assert "const priorityData =" in html
    assert "const roadRiskData =" in html
    assert "const briefsBySubdistrict =" in html
    assert "const theos2PreviewData =" in html
    assert "const sentinel1QuicklookData =" in html
    assert "const demQuicklookData =" in html
    assert "const localDataLibrarySummary =" in html
    assert "const maeSaiPriorityData =" in html
    assert "const maeSaiRoadRiskData =" in html
    assert "const maeSaiFacilityData =" in html
    assert "const maeSaiAccessHotspotData =" in html
    assert "const maeSaiContextQuality =" in html
    assert "const maeSaiSarContext =" in html
    assert "const maeSaiBriefsBySubdistrict =" in html
    assert 'class="app-header"' in html
    assert 'data-dashboard-section="app-header"' in html
    assert 'class="kpi-strip"' in html
    assert 'data-dashboard-section="kpi-strip"' in html
    assert 'class="dashboard-workspace"' in html
    assert 'data-dashboard-section="dashboard-workspace"' in html
    assert 'class="control-panel"' in html
    assert 'class="map-panel"' in html
    assert 'data-dashboard-section="map-panel"' in html
    assert 'class="decision-panel"' in html
    assert 'data-dashboard-section="decision-panel"' in html
    assert 'data-dashboard-section="context-readiness-panel"' in html
    assert 'data-dashboard-section="report-section"' in html
    assert "Fixture demo" in html
    assert "Non-operational" in html
    assert "Real validation blocked" in html
    assert "Static HTML | embedded data | no backend" in html
    assert "Priority Map" in html
    assert "map.invalidateSize" in html
    assert "const mapBoundsPadding = 0.12" in html
    assert "function fitPriorityMapToData" in html
    assert "function settleMapLayout" in html
    assert "function preserveMapViewAfterLayout" in html
    assert "new ResizeObserver(preserveMapViewAfterLayout)" in html
    assert "bounds.pad(mapBoundsPadding)" in html
    assert "ResizeObserver" in html
    assert "bounds.pad(0.18)" not in html
    assert "subdistrict-label" in html
    assert "layer.bindTooltip" in html
    assert "escapeHtml(id)" in html
    assert "TH570901: [0, -11]" in html
    assert "TH570906: [0, 11]" in html
    assert "width: 64px" in html
    assert "minmax(520px, 1fr)" in html
    assert "height: clamp(540px, calc(100vh - 330px), 620px)" in html
    assert "Controls &amp; Scenario" in html
    assert "Fixture context only. Not flood detection, validation, or an official warning." in html
    assert 'class="context-preview-grid"' in html
    assert 'class="app-footer"' in html
    assert 'data-dashboard-section="app-footer"' in html
    assert "Generated: 2025-07-07 08:00 ICT" in html
    assert 'class="validation-metric-grid"' in html
    assert 'class="validation-metric"' in html
    assert "Toy metrics are synthetic fixtures only" in html
    assert "F1 / Dice" in html
    assert "0.67" in html
    assert 'class="brief-summary"' in html
    assert "Data Readiness" in html
    assert "Read This First" in html
    assert "Synthetic inputs demonstrate prioritization and scenarios" in html
    assert "Real Mae Sai validation is blocked" in html
    assert "provider response pending" in html
    assert "Context layers are not flood labels" in html
    assert "Real-data ML remains blocked" in html
    assert "Sentinel-1 SAR Context" in html
    assert 'id="sentinel1-sar-context"' in html
    assert "sentinel1_quicklook_vv.png" in html
    assert "sentinel1_quicklook_vh.png" in html
    assert "SAR context only" in html
    assert "not flood detection" in html
    assert "not validation" in html
    assert "not an official warning" in html
    assert "event timing unresolved unless proven otherwise" in html
    assert "DEM Terrain Context" in html
    assert 'id="dem-terrain-context"' in html
    assert "dem_quicklook.png" in html
    assert "DEM terrain quicklook" in html
    assert "DEM terrain context only" in html
    assert "not flood observation" in html
    assert "not flood label" in html
    assert "not reference mask" in html
    assert "not an official warning" in html
    assert "THEOS-2 Optical Context" in html
    assert "Optical context only; not flood validation or an official warning." in html
    assert "theos2_previews/theos2_preview_" in html
    assert "Local Data Library" in html
    assert 'id="local-data-library"' in html
    assert "sentinel1_sar" in html
    assert "copernicus_dem" in html
    assert "theos2_optical" in html
    assert "Local Sentinel-1 readiness" in html
    assert "Sentinel-1 provenance status" in html
    assert "timing_unresolved" in html
    assert "SAR quicklooks: 2" in html
    assert "DEM readiness" in html
    assert "DEM quicklooks: 1" in html
    assert "terrain context only" in html
    assert "THEOS-2 optical context readiness" in html
    assert "optical context only" in html
    assert "Source files are outside Git and processing remains gated." in html
    assert "local_data_library_manifest.csv" in html
    assert "sentinel1_selected_file_manifest.csv" in html
    assert "sentinel1_provenance_resolved_manifest.csv" in html
    assert "sentinel1_quicklook_manifest.csv" in html
    assert "dem_selected_file_manifest.csv" in html
    assert "dem_quicklook_manifest.csv" in html
    assert "C:\\Users" not in html
    assert "C:/Users" not in html
    assert "official flood observations" not in html
    assert 'id="subdistrict-select"' in html
    assert 'id="scenario-select"' in html
    assert 'id="dataset-mode-select"' in html
    assert "fixture demo" in html
    assert "Mae Sai weak-reference candidate" in html
    assert "Metadata/blocker view" in html
    assert "const datasetModeNotes =" in html
    assert "Mae Sai weak-reference candidate: this mode is separated from the fixture demo" in html
    assert "The weak-reference decision bridge is available" in html
    assert 'id="mae-sai-weak-reference-card"' in html
    assert "b09f96ca-4a60-43e7-9b8d-158022f0e5bf" in html
    assert "20a9c3b8-37df-46d5-81d8-d63c7e460225" in html
    assert "MANUAL-QGIS-MAE-SAI-2024" in html
    assert "ready_for_candidate_metrics" in html
    assert "confirmed_true" in html
    assert "TH570906" in html
    assert "weak_reference_candidate" in html
    assert "real_open_context_joined_with_proxy_vulnerability" in html
    assert "8 ADM3 reporting units" in html
    assert "IoU 0.006079" in html
    assert "F1/Dice 0.012085" in html
    assert "precision 0.038494" in html
    assert "recall 0.007167" in html
    assert "area error -0.813809" in html
    assert "Candidate metrics against manually digitized weak-reference mask" in html
    assert "Not official validation" in html
    assert "Metadata/blocker view: source inventory and file readiness are visible" in html
    assert "dataset-mode-note" in html
    assert 'class="action-filter"' in html
    assert "temporary shelter delta" in html
    assert "road closure delta" in html
    assert "Best intervention effect" in html
    assert "Worst road-closure stress case" in html
    assert "Temporary shelter: -30 people losing 30-min access" in html
    assert "Road closure: +50 people losing 30-min access" in html
    assert 'id="download-current-brief"' in html
    assert 'id="download-filtered-geojson"' in html
    assert "document.getElementById('download-current-brief').disabled = metadataOnly" in html
    assert "document.getElementById('download-filtered-geojson').disabled = metadataOnly" in html
    assert "Download current brief" in html
    assert "Download filtered GeoJSON" in html
    assert "function downloadCurrentActionBrief" in html
    assert "function downloadFilteredGeoJSON" in html
    assert "function downloadText" in html
    assert "new Blob" in html
    assert "_priority_filtered.geojson" in html
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
    assert "function applyDatasetMode" in html
    assert "function renderAllMapLayers" in html
    assert "function updateEvidencePanel" in html
    assert "function updateComparison" in html
    assert "function updateQualityPanel" in html
    assert "const semanticDetailZoom = 12" in html
    assert "function visibleRoadFeatures" in html
    assert "Fixture map detail" in html
    assert "Reporting boundaries only" in html
    assert "function facilityClusterMarker" in html
    assert "function facilityMarker" in html
    assert "candidate_open_with_delay" in html
    assert "facility-cluster-shell" in html
    assert "facility-marker-shell" in html
    assert "hospital" in html
    assert "clinic" in html
    assert "healthcare" in html
    assert "emergency_service" in html
    assert "community_facility" in html
    assert 'id="toggle-focus"' in html
    assert "focusSelected: true" in html
    assert "map.getZoom() >= semanticDetailZoom" in html
    assert 'id="language-en"' in html
    assert 'id="language-th"' in html
    assert "function setLanguage" in html
    assert "แดชบอร์ดการตัดสินใจ FloodGuard" in html
    assert '--font-thai: "Noto Sans Thai"' in html
    assert 'id="sar-evidence-drawer"' in html
    assert "mean_combined_sar_change_score" in html
    assert "Derived ADM3 statistics only" in html
    assert 'class="provenance-summary-grid"' in html
    assert 'id="technical-provenance"' in html
    assert 'id="judge-mode-toggle"' in html
    assert "function setJudgeMode" in html
    assert "Dataset & Selection" in html
    assert "if (state.judgeMode) map.closePopup()" in html
    assert "body.judge-mode .judge-secondary" in html
    assert 'id="mode-warning"' in html
    assert 'class="evidence-grid"' in html
    assert 'id="model-context-panel"' in html
    assert 'data-dashboard-section="model-context-panel"' in html
    assert 'id="panel-modality-used"' in html
    assert "function updateModelContextPanel" in html
    assert "hasDeclaredSarEvidence" in html
    assert "No observation-modality decision metadata is available." in html
    assert "Research fusion candidate" in html
    assert 'data-i18n="model.modality"' in html
    assert 'data-i18n="model.historical"' in html
    assert "ผลการผสานข้อมูลเพื่อการวิจัย" in html
    assert "ความไวต่อน้ำท่วมในอดีต/บริบท" in html
    assert "ไม่ใช่การสังเกตน้ำท่วมปัจจุบัน และไม่ใช่การพยากรณ์" in html
    assert "Research sidecar; not used by FPPS or action class." in html
    assert "SAR only" in html
    assert "SAR + optical" in html
    assert "S2-FIXTURE-CLEAR-001" in html
    assert "no_optical_candidate" in html
    assert "Historical susceptibility/context" in html
    assert "Not observed current flooding. Not a forecast." in html
    assert '"historical_susceptibility_0_100": 87.45' in html
    assert "current_sar_high_historical_low" in html
    assert "uncalibrated_requires_basin_event_target_corpus" in html
    assert "research_sidecar_not_used_by_fpps" in html
    assert 'id="panel-historical-susceptibility"' in html
    assert 'id="panel-historical-warning"' in html
    assert 'id="panel-historical-meta"' in html
    assert 'class="comparison-grid"' in html
    assert 'id="source-quality-panel"' in html
    assert 'id="toggle-facilities"' in html
    assert 'id="toggle-hotspots"' in html
    assert "candidate_closed" in html
    assert "unverified_osm_candidate" in html
    assert "modeled_access_loss_candidate" in html
    assert "--font-sans:" in html
    assert "--radius-md:" in html
    assert "--shadow-md:" in html
    assert "fetch(" not in html


def test_write_static_dashboard_can_render_true_thumbnail_cards(tmp_path: Path) -> None:
    thumbnail_manifest = tmp_path / "theos2_thumbnail_manifest.csv"
    thumbnail_manifest.write_text(
        "\n".join(
            [
                "file_name,source_timestamp,category,sha256,thumbnail_path,thumbnail_format,raster_reader",
                "IMG_T2V_20250730033331_ORTHO_PMS_32-004.tif,2025-07-30T03:33:31Z,Disaster,"
                "aaaaaaaaaaaa,theos2_thumbnails/theos2_thumbnail_004.png,png,rasterio",
            ]
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "dashboard.html"

    write_static_dashboard(
        OUTPUTS / "priority_subdistricts.geojson",
        OUTPUTS / "road_risk.geojson",
        OUTPUTS / "validation_summary.md",
        OUTPUTS / "action_brief_FG-TB-001.md",
        output_path,
        theos2_preview_manifest_path=thumbnail_manifest,
    )

    html = output_path.read_text(encoding="utf-8")
    assert "theos2_thumbnails/theos2_thumbnail_004.png" in html
    assert "True PNG thumbnail via rasterio" in html
    assert "Metadata SVG preview card" not in html
    assert "not flood validation or an official warning" in html


def test_dashboard_output_contract_path() -> None:
    assert (OUTPUTS / "dashboard.html").as_posix().endswith("outputs/dashboard.html")
