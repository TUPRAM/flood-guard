"use client";

import Image from "next/image";
import { useCallback, useEffect, useMemo, useState } from "react";

import { GeoMap } from "@/components/geo-map";
import { LanguageToggle } from "@/components/language-toggle";
import { ScoreBar } from "@/components/score-bar";
import { StatePill } from "@/components/state-pill";
import { commandRankPositions, resolveCommandSelection, searchRankedAreas, toggleCommandClass } from "@/lib/command-filter";
import { downloadText } from "@/lib/download";
import { formatConfidence, formatNumber, formatSourceTime, formatTopReason } from "@/lib/format";
import { loadMaeSaiRoadDetail } from "@/lib/data-provider";
import { visibleLayerAttributions } from "@/lib/map-attribution";
import { formatServerDelta, scenarioMapPresentation } from "@/lib/scenario-presentation";
import type { AreaRecord, FeatureCollection, FloodGuardData, ScenarioId } from "@/lib/types";
import { useFloodGuardData } from "@/lib/use-floodguard-data";
import { useLanguage } from "@/lib/use-language";

const ACTION_CLASSES = ["A", "B", "C", "D", "E"] as const;
const COMMAND_AREA_STORAGE_KEY = "floodguard:command:selected-area:v1";
const COMMAND_TABS = ["summary", "facilities", "scenario", "verification", "method"] as const;
type CommandTab = typeof COMMAND_TABS[number];

const ACTION_TEXT = {
  A: { en: "Prepare life-safety resources and verify the area first.", th: "เตรียมทรัพยากรเพื่อความปลอดภัยและตรวจสอบพื้นที่เป็นลำดับแรก" },
  B: { en: "Verify critical links and prepare continuity options.", th: "ตรวจสอบเส้นทางสำคัญและเตรียมทางเลือกเพื่อความต่อเนื่อง" },
  C: { en: "Verify essential-service access and backup arrangements.", th: "ตรวจสอบการเข้าถึงบริการจำเป็นและแผนสำรอง" },
  D: { en: "Prioritize longer-term resilience measures.", th: "จัดลำดับมาตรการเสริมความยืดหยุ่นระยะยาว" },
  E: { en: "Monitor and obtain better evidence before action.", th: "ติดตามและเพิ่มหลักฐานก่อนตัดสินใจ" },
} as const;

export function offlineBrief(area: AreaRecord, status: FloodGuardData["status"]): string {
  const action = ACTION_TEXT[area.action_class as keyof typeof ACTION_TEXT] ?? ACTION_TEXT.E;
  const disclosure = status.dataset_mode === "official_input"
    ? "Agency data input / ข้อมูลนำเข้าจากหน่วยงาน"
    : "Mae Sai planning data / ข้อมูลเพื่อการวางแผนแม่สาย";
  return `# FloodGuard bilingual action brief / เอกสารสรุปการดำเนินการสองภาษา

${disclosure} — Confirm current conditions and instructions with DDPM and local authorities before action. / ก่อนดำเนินการ โปรดยืนยันสถานการณ์และคำแนะนำปัจจุบันกับ ปภ. และหน่วยงานท้องถิ่น

## Area / พื้นที่

- ${area.area_name_en}
- ${area.area_name_th}
- ID: ${area.area_id}

## Priority / ลำดับความสำคัญ

- FPPS: ${area.fpps_0_100.toFixed(2)}
- Action class / ชั้นการดำเนินการ: ${area.action_class}
- Confidence / ความเชื่อมั่น: ${area.confidence_class} / ${formatConfidence(area.confidence_class, "th")}
- Action reason code: ${area.action_reason_code}
- Canonical reason: ${area.top_reason}
- Display reason / เหตุผล: ${planningSourceName(area.top_reason)} / ${formatTopReason(area.action_class, area.top_reason, "th")}

## Access and equity / การเข้าถึงและความเสมอภาค

- People losing 30-minute access (modelled planning estimate): ${area.people_losing_30_min_access}
- Equity gap ratio: ${area.equity_gap_ratio ?? "unavailable"}
- Method: nearest-facility shortest-path threshold analysis; not capacity-aware 2SFCA.

## Recommended planning action / ข้อเสนอเพื่อการวางแผน

- ${action.en}
- ${action.th}

## Provenance / แหล่งที่มา

- Source: ${area.source_name}
- Source timestamp: ${area.source_timestamp}
- Generated at: ${area.generated_at}
- Data version: ${area.data_version}
- Dataset mode: ${area.dataset_mode}
- Operational status: ${area.operational_status}
- Official warning: ${area.official_warning}
- Evidence context ID: ${area.evidence_context_id ?? status.evidence_context_id ?? "not supplied"}
- Study area: ${status.study_area}
- Assumptions: ${area.assumptions.join("; ")}
`;
}

type CommandExportData = Pick<FloodGuardData, "areas" | "areaFeatures" | "facilityFeatures" | "readiness" | "status" | "evidenceContext" | "evidenceRecord">;

export function buildFilteredAreaGeoJson(data: CommandExportData, activeClasses: ReadonlySet<string>) {
  const visibleIds = new Set(data.areas.filter((area) => activeClasses.has(area.action_class)).map((area) => area.area_id));
  const areaById = new Map(data.areas.map((area) => [area.area_id, area]));
  return {
    type: data.areaFeatures.type,
    name: "mae_sai_planning_areas",
    evidence_context: data.evidenceContext,
    evidence_record: data.evidenceRecord,
    features: data.areaFeatures.features
      .filter((feature) => visibleIds.has(String(feature.properties.area_id)))
      .map((feature) => {
        const area = areaById.get(String(feature.properties.area_id));
        return {
          ...feature,
          properties: area ? {
            ...area,
            ...feature.properties,
            study_area: data.status.study_area,
          } : { ...feature.properties },
        };
      }),
  };
}

export function buildVerificationQueueExport(data: CommandExportData, selectedAreaId: string) {
  return {
    schema_version: data.status.schema_version,
    dataset_mode: data.status.dataset_mode,
    operational_status: data.status.operational_status,
    official_warning: data.status.official_warning,
    evidence_context_id: data.status.evidence_context_id,
    study_area: data.status.study_area,
    data_version: data.status.data_version,
    source_timestamp: data.status.source_timestamp,
    generated_at: data.status.generated_at,
    evidence_context: data.evidenceContext,
    evidence_record: data.evidenceRecord,
    selected_area_id: selectedAreaId,
    readiness_checks: data.readiness.filter((row) => row.status !== "ready"),
    facility_records: data.facilityFeatures.features.filter(
      (feature) => String(feature.properties.area_id ?? "") === selectedAreaId,
    ),
  };
}

function planningSourceName(sourceName: string): string {
  return sourceName
    .replace(/\bcandidate\b/gi, "planning")
    .replace(/\bfixture\b/gi, "reference")
    .replace(/\bdemo\b/gi, "planning")
    .replace(/\bsynthetic\b/gi, "modelled")
    .replace(/\bnon[-_ ]operational\b/gi, "planning-only");
}

function planningAssumptions(area: AreaRecord, language: "en" | "th" = "en"): string[] {
  if (area.candidate_evidence) {
    if (language === "th") {
      return [
        "โอกาสน้ำท่วมใช้บริบท Sentinel-1 และข้อมูลอ้างอิงข้ามพรมแดน โปรดยืนยันสภาพปัจจุบันกับแหล่งข้อมูลทางการ",
        "การสัมผัสใช้ WorldPop ส่วนผลกระทบต่อถนนและการเข้าถึงเป็นค่าประมาณเพื่อการวางแผน",
        "โปรดยืนยันบทบาท ความจุ การเข้าถึงสถานที่ และสภาพถนนปัจจุบันในพื้นที่",
      ];
    }
    return [
      "Flood likelihood uses Sentinel-1 context and a nearby cross-border reference; confirm current conditions with official sources.",
      "Exposure uses WorldPop, while road disruption and access loss are modelled planning estimates.",
      "Facility roles, capacity, accessibility, and current road conditions require local confirmation.",
    ];
  }
  return area.assumptions.map((assumption) => planningSourceName(assumption));
}

export function CommandWorkspace() {
  const data = useFloodGuardData({ studyArea: "mae_sai_candidate_v1", role: "command" });
  const [language, setLanguage] = useLanguage("en");
  const [selectedId, setSelectedId] = useState("");
  const [areaQuery, setAreaQuery] = useState("");
  const [activeTab, setActiveTab] = useState<CommandTab>("summary");
  const [scenario, setScenario] = useState<ScenarioId>("baseline");
  const [activeClasses, setActiveClasses] = useState<Set<string>>(() => new Set(ACTION_CLASSES));
  const [showRoads, setShowRoads] = useState(true);
  const [showFacilities, setShowFacilities] = useState(true);
  const [showAccess, setShowAccess] = useState(true);
  const [selectedRoadDetail, setSelectedRoadDetail] = useState<{ areaId: string; features?: FeatureCollection }>();
  const [evidenceDrawerOpen, setEvidenceDrawerOpen] = useState(true);
  const [briefError, setBriefError] = useState(false);
  const th = language === "th";
  const selected = resolveCommandSelection(data.areas, selectedId) ?? data.areas[0];
  const candidateApiStateUsable = data.dataOrigin === "api"
    && data.status.study_area === "mae_sai_candidate_v1"
    && data.status.data_state === "stale";
  const supportsScenarios = data.scenarioState === "ready"
    && (data.status.data_state === "ready" || candidateApiStateUsable)
    && data.availableScenarios.length > 1
    && (
      (data.status.dataset_mode === "fixture_demo" && data.status.study_area === "fixture_thailand_demo")
      || (data.dataOrigin === "api" && data.status.study_area === "mae_sai_candidate_v1")
    );
  const totalRoadCount = data.areas.reduce(
    (total, area) => total + (area.candidate_evidence?.road_count ?? 0),
    0,
  ) || data.roadFeatures.features.length;
  const effectiveRoadFeatures = useMemo(
    () => mergeRoadCollections(data.roadFeatures, selectedRoadDetail, selected.area_id),
    [data.roadFeatures, selected.area_id, selectedRoadDetail],
  );
  const roadDetailState: "bundled" | "loading" | "ready" | "unavailable" = data.dataOrigin !== "api"
    ? "bundled"
    : selectedRoadDetail?.areaId !== selected.area_id
      ? "loading"
      : selectedRoadDetail.features
        ? "ready"
        : "unavailable";
  const roadLayerAvailable = data.layers.some((layer) => layer.layer_id === "road_risk" && ["ready", "stale"].includes(layer.data_state)) && effectiveRoadFeatures.features.length > 0;
  const facilityLayerAvailable = data.layers.some((layer) => layer.layer_id === "facilities" && ["ready", "stale"].includes(layer.data_state)) && data.facilityFeatures.features.length > 0;
  const accessLayerAvailable = data.layers.some((layer) => layer.layer_id === "access_hotspots" && ["ready", "stale"].includes(layer.data_state)) && data.accessFeatures.features.length > 0;
  const visibleMapLayerIds = useMemo(() => {
    const layerIds = new Set(["priority_areas"]);
    if (roadLayerAvailable && showRoads) layerIds.add("road_risk");
    if (facilityLayerAvailable && showFacilities) layerIds.add("facilities");
    if (accessLayerAvailable && showAccess) layerIds.add("access_hotspots");
    return layerIds;
  }, [accessLayerAvailable, facilityLayerAvailable, roadLayerAvailable, showAccess, showFacilities, showRoads]);
  const mapAttributions = useMemo(
    () => visibleLayerAttributions(data.layers, visibleMapLayerIds),
    [data.layers, visibleMapLayerIds],
  );
  const activeScenario: ScenarioId = supportsScenarios && data.availableScenarios.includes(scenario)
    ? scenario
    : "baseline";
  const availableCommandTabs: CommandTab[] = activeScenario !== "baseline"
    ? [...COMMAND_TABS]
    : COMMAND_TABS.filter((tab) => tab !== "scenario");
  const displayedTab: CommandTab = availableCommandTabs.includes(activeTab) ? activeTab : "summary";
  const scenarioResult = selected.scenario_results[activeScenario];
  const baselineScenarioResult = selected.scenario_results.baseline;
  const scenarioPresentation = scenarioMapPresentation(selected.action_class, activeScenario, scenarioResult);
  const rankedAreas = searchRankedAreas(data.areas, activeClasses, areaQuery);
  const allRankedAreas = searchRankedAreas(data.areas, activeClasses, "");
  const canonicalRanks = useMemo(() => commandRankPositions(data.areas), [data.areas]);
  const selectedRank = allRankedAreas.findIndex((area) => area.area_id === selected.area_id) + 1;
  const availableActionClasses = [...new Set(data.areas.map((area) => area.action_class))];
  const roadEvidenceState = data.layers.find((layer) => layer.layer_id === "road_risk")?.evidence_state;
  const roadSegmentEvidenceReady = roadEvidenceState?.granularity === "road_segment"
    && roadEvidenceState.gate_state === "ready"
    && data.readiness.some((row) => row.check_id === "segment_raster_intersection" && row.status === "ready");
  const selectedRoadCount = selected.candidate_evidence?.road_count
    ?? effectiveRoadFeatures.features.filter((feature) => feature.properties.area_id === selected.area_id).length;
  const selectedFacilityCount = data.facilityFeatures.features.filter((feature) => feature.properties.area_id === selected.area_id).length;
  const selectedFacilities = data.facilityFeatures.features.filter(
    (feature) => String(feature.properties.area_id ?? "") === selected.area_id,
  );
  const verificationQueue = [
    ...data.readiness.filter((row) => row.status !== "ready").map((row) => ({
      id: row.check_id,
      title: planningSourceName(row.source),
      detail: planningSourceName(row.reason_blocked),
      severity: row.severity,
    })),
    ...(selectedFacilities.length > 0 && !data.readiness.some((row) => row.check_id === "facility_verification" && row.status === "ready") ? [{
      id: `facilities-${selected.area_id}`,
      title: th ? "ยืนยันบทบาทและการเปิดใช้งานสถานที่" : "Verify facility role and operation",
      detail: th ? `${selectedFacilities.length} แห่งต้องตรวจสอบกับหน่วยงานท้องถิ่น` : `${selectedFacilities.length} mapped sites require local verification.`,
      severity: "critical",
    }] : []),
  ];
  const selectArea = useCallback((areaId: string) => setSelectedId(areaId), []);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      try {
        const persistedId = window.localStorage.getItem(COMMAND_AREA_STORAGE_KEY);
        const resolved = resolveCommandSelection(data.areas, persistedId);
        if (resolved) setSelectedId(resolved.area_id);
      } catch {
        const resolved = resolveCommandSelection(data.areas);
        if (resolved) setSelectedId(resolved.area_id);
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, [data.areas]);

  useEffect(() => {
    if (!data.areas.some((area) => area.area_id === selectedId)) return;
    try {
      window.localStorage.setItem(COMMAND_AREA_STORAGE_KEY, selectedId);
    } catch {
      // Storage may be unavailable; the valid in-memory selection remains active.
    }
  }, [data.areas, selectedId]);

  useEffect(() => {
    let active = true;
    if (
      data.dataOrigin !== "api"
      || !data.apiBase
      || data.status.study_area !== "mae_sai_candidate_v1"
      || !selected.candidate_evidence
    ) {
      return () => { active = false; };
    }
    void loadMaeSaiRoadDetail(
      data.apiBase,
      selected.area_id,
      selected.candidate_evidence.road_count,
    ).then((features) => {
      if (!active) return;
      setSelectedRoadDetail({ areaId: selected.area_id, features });
    }).catch(() => {
      if (!active) return;
      setSelectedRoadDetail({ areaId: selected.area_id });
    });
    return () => { active = false; };
  }, [data.apiBase, data.dataOrigin, data.status.study_area, selected]);

  const toggleClass = (actionClass: string) => {
    const next = toggleCommandClass(
      activeClasses,
      actionClass,
      selected.area_id,
      data.areas,
    );
    setActiveClasses(next.activeClasses);
    setSelectedId(next.selectedId);
  };

  const downloadFilteredGeoJson = () => {
    const filtered = buildFilteredAreaGeoJson(data, activeClasses);
    downloadText("floodguard-mae-sai-planning-areas.geojson", JSON.stringify(filtered, null, 2), "application/geo+json");
  };

  const downloadBrief = () => {
    setBriefError(false);
    try {
      downloadText(`floodguard-${selected.area_id}-planning-brief.md`, offlineBrief(selected, data.status), "text/markdown;charset=utf-8");
    } catch {
      setBriefError(true);
    }
  };

  const downloadVerificationQueue = () => {
    downloadText(
      `floodguard-${selected.area_id}-verification-queue.json`,
      JSON.stringify(buildVerificationQueueExport(data, selected.area_id), null, 2),
      "application/json",
    );
  };

  return (
    <main className="command-page" lang={language}>
      <header className="command-header command-product-header">
        <a href="/command/" className="brand brand-light"><Image src="/floodguard-logo.png" alt="" width={40} height={40} priority /><span><b>FloodGuard</b><small>{th ? "พื้นที่ทำงานวางแผน" : "Planning workspace"}</small></span></a>
        <nav aria-label="Product surfaces"><a href="/public/">{th ? "ประชาชน" : "Public"}</a><a className="active" href="/command/">{th ? "การวางแผน" : "Planning"}</a><a href="/studio/">Studio</a></nav>
        <LanguageToggle language={language} onChange={setLanguage} />
      </header>
      <section className="command-context-bar" aria-label={th ? "บริบทข้อมูลการวางแผน" : "Planning data context"}>
        <strong className="command-context-label">{th ? "ข้อมูลเพื่อการวางแผน" : "Planning intelligence"}</strong>
        <dl className="command-context-metadata">
          <div><dt>{th ? "เวลาข้อมูล" : "Source time"}</dt><dd>{formatSourceTime(selected.source_timestamp, language)} ICT</dd></div>
          <div><dt>{th ? "ความเชื่อมั่น" : "Confidence"}</dt><dd>{formatConfidence(selected.confidence_class, language)}</dd></div>
        </dl>
        <p className="command-context-advisory">{th ? "ยืนยันสภาพถนน สถานที่ และคำแนะนำปัจจุบันกับ ปภ. และหน่วยงานท้องถิ่นก่อนดำเนินการ" : "Confirm current road and facility conditions, and follow DDPM and local-authority instructions before action."}</p>
      </section>

      <div className="small-screen-command-note command-summary-card card">
        <h1>{th ? "สรุปพื้นที่ทำงานวางแผน" : "Planning workspace summary"}</h1>
        <p>{th ? "ใช้หน้าจอแท็บเล็ตหรือเดสก์ท็อปเพื่อดูแผนที่และแผงควบคุมทั้งหมด" : "Use a tablet or desktop for the full map and control workspace."}</p>
        <dl><div><dt>{th ? "พื้นที่" : "Area"}</dt><dd>{th ? selected.area_name_th : selected.area_name_en}</dd></div><div><dt>FPPS</dt><dd>{selected.fpps_0_100.toFixed(1)} / {selected.action_class}</dd></div></dl>
      </div>

      <div className="command-workspace command-dashboard-grid">
        <aside className="control-rail command-control-panel" aria-label={th ? "ตัวควบคุม" : "Controls"}>
          <section className="rail-section ranked-areas" aria-labelledby="ranked-areas-title">
            <div className="rail-section-heading"><p className="rail-label" id="ranked-areas-title">{th ? "ลำดับ FPPS" : "FPPS ranking"}</p><span>{rankedAreas.length}/{data.areas.length}</span></div>
            <label className="area-search">
              <span>{th ? "ค้นหาพื้นที่" : "Search areas"}</span>
              <input type="search" value={areaQuery} onChange={(event) => setAreaQuery(event.target.value)} placeholder={th ? "ชื่อหรือรหัสพื้นที่" : "Name or area ID"} />
            </label>
            <ol>
              {rankedAreas.map((area, index) => (
                <li key={area.area_id}>
                  <button type="button" className={area.area_id === selected.area_id ? "selected" : ""} aria-current={area.area_id === selected.area_id ? "true" : undefined} onClick={() => selectArea(area.area_id)}>
                    <span className="rank-number">{String(canonicalRanks.get(area.area_id) ?? index + 1).padStart(2, "0")}</span>
                    <span className="rank-name"><b>{th ? area.area_name_th : area.area_name_en}</b><small>{area.area_id}</small></span>
                    <span className={`rank-score class-${area.action_class.toLowerCase()}`}>
                      <b>{area.fpps_0_100.toFixed(1)}</b>
                      <small>{th ? "ชั้น" : "Class"} {area.action_class}</small>
                      {activeScenario !== "baseline" && (
                        <small className={`rank-scenario-delta scenario-${scenarioMapPresentation(area.action_class, activeScenario, area.scenario_results[activeScenario]).tone}`}>
                          {formatServerDelta(area.scenario_results[activeScenario].delta)} {th ? "การเข้าถึง" : "access"}
                        </small>
                      )}
                    </span>
                  </button>
                </li>
              ))}
            </ol>
            {rankedAreas.length === 0 && <p className="rail-help" role="status">{th ? "ไม่พบพื้นที่ที่ตรงกัน" : "No matching areas."}</p>}
          </section>
          <div className="rail-section">
            <p className="rail-label">{th ? "สถานการณ์เพื่อการวางแผน" : "Planning scenario"}</p>
            <select value={activeScenario} disabled={!supportsScenarios} onChange={(event) => setScenario(event.target.value as ScenarioId)} aria-label={th ? "เลือกสถานการณ์" : "Select scenario"}>
              <option value="baseline">{th ? "ค่าฐาน" : "Baseline"}</option>
              {supportsScenarios && data.availableScenarios.includes("add_temporary_shelter") && <option value="add_temporary_shelter">{th ? "ตัวเลือกสถานที่ชั่วคราว" : "Temporary facility option"}</option>}
              {supportsScenarios && data.availableScenarios.includes("close_road") && <option value="close_road">{th ? "สถานการณ์ปิดถนน" : "Road-closure scenario"}</option>}
            </select>
            <p className="rail-help">{supportsScenarios ? (th ? "ค่าประมาณสถานการณ์ใช้ข้อมูลการวางแผนที่เผยแพร่ในมุมมองนี้" : "Scenario estimates use the planning evidence published in this view.") : (th ? "มุมมองการวางแผนที่เผยแพร่นี้ยังไม่รวมการเปรียบเทียบสถานการณ์" : "Scenario comparison is not included in this published planning view.")}</p>
          </div>
          {availableActionClasses.length > 1 && <fieldset className="rail-section class-filters"><legend>{th ? "กรองชั้น A–E" : "A–E filters"}</legend><div>{availableActionClasses.map((actionClass) => <button type="button" aria-pressed={activeClasses.has(actionClass)} className={activeClasses.has(actionClass) ? `active class-${actionClass.toLowerCase()}` : ""} key={actionClass} onClick={() => toggleClass(actionClass)}>{actionClass}</button>)}</div></fieldset>}
          <fieldset className="rail-section layer-toggles"><legend>{th ? "ชั้นข้อมูล" : "Layers"}</legend><label><input type="checkbox" checked readOnly /> {th ? "พื้นที่ FPPS" : "FPPS areas"}</label><label className={roadLayerAvailable ? undefined : "disabled"}><input type="checkbox" checked={roadLayerAvailable && showRoads} disabled={!roadLayerAvailable} onChange={(event) => setShowRoads(event.target.checked)} /> {roadLayerAvailable ? (roadSegmentEvidenceReady ? (th ? `ความเสี่ยงถนนรายช่วง (${totalRoadCount.toLocaleString()})` : `Road-segment risk (${totalRoadCount.toLocaleString()})`) : (th ? `โครงข่ายถนนเพื่อบริบท (${totalRoadCount.toLocaleString()})` : `Road network context (${totalRoadCount.toLocaleString()})`)) : (th ? "ถนน (ไม่มีข้อมูล)" : "Roads (unavailable)")}</label><label className={facilityLayerAvailable ? undefined : "disabled"}><input type="checkbox" checked={facilityLayerAvailable && showFacilities} disabled={!facilityLayerAvailable} onChange={(event) => setShowFacilities(event.target.checked)} /> {facilityLayerAvailable ? (th ? `สถานที่ที่ต้องยืนยัน (${data.facilityFeatures.features.length})` : `Facilities to verify (${data.facilityFeatures.features.length})`) : (th ? "สถานที่ (ไม่มีข้อมูล)" : "Facilities (unavailable)")}</label><label className={accessLayerAvailable ? undefined : "disabled"}><input type="checkbox" checked={accessLayerAvailable && showAccess} disabled={!accessLayerAvailable} onChange={(event) => setShowAccess(event.target.checked)} /> {accessLayerAvailable ? (th ? "หลักฐานการเข้าถึง" : "Access evidence") : (th ? "หลักฐานการเข้าถึง (ไม่มี)" : "Access evidence (unavailable)")}</label></fieldset>
          <section className="rail-section planning-safeguard" aria-labelledby="planning-safeguard-title">
            <p className="rail-label" id="planning-safeguard-title">{th ? "การยืนยันก่อนดำเนินการ" : "Before action"}</p>
            <p>{th ? "ตรวจสอบสภาพถนน บทบาทและความจุสถานที่ รวมถึงคำแนะนำจาก ปภ. และหน่วยงานท้องถิ่น" : "Verify road conditions, facility role and capacity, and current DDPM or local-authority instructions."}</p>
          </section>
        </aside>

        <section className="map-workspace command-map-panel" aria-label={th ? "พื้นที่ทำงานแผนที่" : "Map workspace"}>
          <div className="map-workspace-heading"><div><p className="eyebrow">{th ? "พื้นที่ทำงานวางแผน" : "Planning workspace"}</p><h1>{th ? selected.area_name_th : selected.area_name_en}</h1></div><span>{selectedRank > 0 ? `#${selectedRank} FPPS` : "—"} · {th ? "เลือกพื้นที่เพื่อซิงค์หลักฐาน" : "select an area to synchronize evidence"}</span></div>
          <GeoMap areas={data.areas} selectedId={selected.area_id} onSelect={selectArea} language={language} showRoads={roadLayerAvailable && showRoads} showFacilities={facilityLayerAvailable && showFacilities} showAccess={accessLayerAvailable && showAccess} classFilter={activeClasses} height="100%" areaFeatures={data.areaFeatures} roadFeatures={effectiveRoadFeatures} regionalRoadCount={data.roadFeatures.features.length} roadDatasetTotal={totalRoadCount} roadDetailState={roadDetailState} facilityFeatures={data.facilityFeatures} accessFeatures={data.accessFeatures} contextFeatures={data.contextFeatures} datasetMode={data.status.dataset_mode} scenarioId={activeScenario} showSelectionSheet={false} attributions={mapAttributions} visualPalette="public-blue" enableBasemaps audience="staff" roadSegmentEvidenceReady={roadSegmentEvidenceReady} />
          {supportsScenarios && activeScenario !== "baseline" && <div className="scenario-delta-strip" aria-live="polite" data-scenario-tone={scenarioPresentation.tone}><span>{activeScenario === "add_temporary_shelter" ? (th ? "ตัวเลือกสถานที่ชั่วคราว" : "Temporary facility option") : (th ? "สถานการณ์ปิดถนน" : "Road-closure scenario")}</span><b>{formatNumber(scenarioResult.people_losing_30_min_access, language)} {th ? "คนสูญเสียการเข้าถึง 30 นาที" : "people lose 30-min access"}</b><strong className={scenarioPresentation.tone}>{formatServerDelta(scenarioResult.delta)} {th ? "เทียบค่าฐาน" : "vs baseline"}</strong></div>}
          <aside className={`tablet-evidence-drawer ${evidenceDrawerOpen ? "open" : "closed"}`} aria-label={th ? "ลิ้นชักหลักฐานพื้นที่" : "Area evidence drawer"}>
            <button type="button" className="tablet-evidence-toggle" aria-expanded={evidenceDrawerOpen} aria-controls="command-tablet-evidence" onClick={() => setEvidenceDrawerOpen((open) => !open)}>
              <span><small>{th ? "หลักฐานพื้นที่" : "Area evidence"} · {selected.area_id}</small><b>{th ? selected.area_name_th : selected.area_name_en}</b></span>
              <strong>FPPS {selected.fpps_0_100.toFixed(1)} · {th ? "ชั้น" : "Class"} {selected.action_class}</strong>
              <span aria-hidden="true">{evidenceDrawerOpen ? "−" : "+"}</span>
            </button>
            <div id="command-tablet-evidence" className="tablet-evidence-body" hidden={!evidenceDrawerOpen} aria-live="polite">
              <p>{formatTopReason(selected.action_class, selected.top_reason, language)}</p>
              <dl>
                <div><dt>{th ? "ค่าฐาน: สูญเสียการเข้าถึง" : "Baseline access loss"}</dt><dd>{formatNumber(baselineScenarioResult.people_losing_30_min_access, language)}</dd></div>
                <div><dt>{th ? "ช่วงถนนที่วิเคราะห์" : "Road segments analysed"}</dt><dd>{selectedRoadCount.toLocaleString()}</dd></div>
                <div><dt>{th ? "สถานที่สำคัญ" : "Important facilities"}</dt><dd>{selectedFacilityCount}</dd></div>
                <div><dt>{th ? "ความเชื่อมั่น" : "Confidence"}</dt><dd>{formatConfidence(selected.confidence_class, language)}</dd></div>
              </dl>
              <small>{supportsScenarios ? (th ? "FPPS และชั้น A–E เป็นตัวชี้วัดการวางแผน สถานการณ์เปรียบเทียบเฉพาะผลลัพธ์การเข้าถึง" : "FPPS and A–E class are published planning indicators; scenario comparisons change access results only.") : (th ? "ข้อมูลแม่สายมีความเชื่อมั่นต่ำ โปรดยืนยันบทบาทและความจุของสถานที่ รวมถึงสภาพถนนปัจจุบันกับหน่วยงานท้องถิ่น" : "Mae Sai planning evidence has low confidence. Confirm facility role and capacity, and current road conditions, with local authorities.")}</small>
            </div>
          </aside>
        </section>

        <aside className="decision-panel command-insight-panel command-release-panel" aria-label={th ? "หลักฐานการวางแผน" : "Planning evidence"} data-scenario-id={activeScenario} data-scenario-tone={scenarioPresentation.tone}>
          <div className="decision-title" aria-live="polite"><div><p className="eyebrow">{th ? "หลักฐานพื้นที่" : "Area evidence"} · {selected.area_id}</p><h2>{th ? selected.area_name_th : selected.area_name_en}</h2><StatePill tone="caution">{formatConfidence(selected.confidence_class, language)} {th ? "ความเชื่อมั่น" : "confidence"}</StatePill></div><span className={`decision-class class-${selected.action_class.toLowerCase()}`} aria-label={`${th ? "ชั้น" : "Class"} ${selected.action_class}`}>{selected.action_class}</span></div>
          <div className="command-tabs" role="tablist" aria-label={th ? "มุมมองหลักฐาน" : "Evidence views"}>
            {availableCommandTabs.map((tab, index) => (
              <button
                type="button"
                role="tab"
                id={`command-tab-${tab}`}
                aria-selected={displayedTab === tab}
                aria-controls="command-tab-panel"
                tabIndex={displayedTab === tab ? 0 : -1}
                key={tab}
                onClick={() => setActiveTab(tab)}
                onKeyDown={(event) => {
                  if (!(["ArrowLeft", "ArrowRight", "Home", "End"] as string[]).includes(event.key)) return;
                  event.preventDefault();
                  const nextIndex = event.key === "Home" ? 0
                    : event.key === "End" ? availableCommandTabs.length - 1
                      : (index + (event.key === "ArrowRight" ? 1 : -1) + availableCommandTabs.length) % availableCommandTabs.length;
                  const nextTab = availableCommandTabs[nextIndex];
                  setActiveTab(nextTab);
                  event.currentTarget.parentElement?.querySelector<HTMLButtonElement>(`#command-tab-${nextTab}`)?.focus();
                }}
              >
                {commandTabLabel(tab, language)}
              </button>
            ))}
          </div>

          <section className="command-tab-panel" role="tabpanel" id="command-tab-panel" aria-labelledby={`command-tab-${displayedTab}`}>
            {displayedTab === "summary" && <>
              <div className="fpps-block"><span>FPPS</span><b>{selected.fpps_0_100.toFixed(1)}</b><small>/ 100</small></div>
              <p className="top-reason">{formatTopReason(selected.action_class, selected.top_reason, language)}</p>
              <dl className="evidence-grid"><div><dt>{th ? "สูญเสียการเข้าถึง 30 นาที · แบบจำลอง" : "30-min access loss · modelled"}</dt><dd>{formatNumber(scenarioResult.people_losing_30_min_access, language)}</dd></div><div><dt>{th ? "อัตราช่องว่างความเสมอภาค · แบบจำลอง" : "Equity-gap ratio · modelled"}</dt><dd>{formatNumber(scenarioResult.equity_gap_ratio, language, 2)}</dd></div><div><dt>{th ? "ช่วงโครงข่ายถนน" : "Road-network segments"}</dt><dd>{roadLayerAvailable ? selectedRoadCount.toLocaleString() : (th ? "ไม่มีข้อมูล" : "Unavailable")}</dd></div><div><dt>{th ? "สถานที่ที่ต้องยืนยัน" : "Facilities to verify"}</dt><dd>{facilityLayerAvailable ? selectedFacilityCount : (th ? "ไม่มีข้อมูล" : "Unavailable")}</dd></div></dl>
              <article className="recommended-action"><p className="eyebrow">{th ? "ข้อเสนอเพื่อการวางแผน" : "Planning action"}</p><p>{ACTION_TEXT[selected.action_class as keyof typeof ACTION_TEXT]?.[language] ?? ACTION_TEXT.E[language]}</p></article>
            </>}

            {displayedTab === "facilities" && <>
              <h3>{th ? "สถานที่และการเข้าถึง" : "Facilities & access"}</h3>
              <p className="tab-guidance">{th ? "ยืนยันบทบาท การเปิดใช้งาน ความจุ และการเข้าถึงกับหน่วยงานท้องถิ่น" : "Confirm role, operation, capacity, and accessibility with local authorities."}</p>
              {selectedFacilities.length > 0 ? <ul className="command-facility-list">
                {selectedFacilities.map((feature, index) => {
                  const properties = feature.properties ?? {};
                  const facilityType = String(properties.facility_type ?? "community_facility");
                  const name = String(properties.facility_name || properties.facility_id || (th ? "สถานที่" : "Facility"));
                  const rawVerification = String(properties.verification_status || properties.candidate_status || "").toLowerCase();
                  const verification = facilityType === "shelter_candidate"
                    ? (th ? "พื้นที่พักพิงที่เป็นไปได้ - ยังไม่ยืนยัน" : "Possible shelter site - unverified")
                    : ["authoritative", "verified", "confirmed", "locally_confirmed", "official_confirmed"].includes(rawVerification)
                      ? (th ? "ยืนยันแล้ว" : "Verified")
                      : (th ? "ยังไม่ยืนยัน" : "Unverified");
                  const operation = commandFacilityOperationLabel(properties, language);
                  const source = planningSourceName(String(properties.source_name || properties.source || (th ? "ไม่ระบุแหล่งที่มา" : "Source not supplied")));
                  const sourceTimestamp = typeof properties.source_timestamp === "string"
                    ? formatSourceTime(properties.source_timestamp, language)
                    : (th ? "ไม่ระบุ" : "Not supplied");
                  return <li key={String(properties.facility_id ?? `${selected.area_id}-${index}`)}><b>{name}</b><span>{facilityType === "shelter_candidate" ? verification : facilityType.replaceAll("_", " ")}</span><small>{facilityType === "shelter_candidate" ? operation : `${verification} · ${operation}`}</small><small>{th ? "แหล่งที่มา" : "Source"}: {source}</small><small>{th ? "วันที่ของแหล่งข้อมูล" : "Source date"}: {sourceTimestamp}</small></li>;
                })}
              </ul> : <p>{th ? "ไม่มีสถานที่ที่ทำแผนที่ในพื้นที่นี้" : "No facilities are mapped in this area."}</p>}
              <dl className="access-summary"><div><dt>{th ? "การสูญเสียการเข้าถึง 30 นาที" : "30-minute access loss"}</dt><dd>{formatNumber(selected.people_losing_30_min_access, language)} {th ? "คน · แบบจำลอง" : "people · modelled"}</dd></div><div><dt>{th ? "วิธี" : "Method"}</dt><dd>{th ? "เส้นทางสั้นที่สุดไปยังสถานที่ที่เลือก" : "Shortest path to a selected facility"}</dd></div><div><dt>{th ? "ข้อจำกัด" : "Assumptions"}</dt><dd>{th ? "ไม่คำนึงถึงความจุ และยังไม่ยืนยันการเปิดใช้งานหรือสภาพถนนปัจจุบัน" : "Not capacity-aware; current facility operation and road conditions are unconfirmed."}</dd></div></dl>
              <article className="road-context-card"><h3>{th ? "โครงข่ายถนนเพื่อบริบท" : "Road network context"}</h3><p>{roadSegmentEvidenceReady ? (th ? "มีหลักฐานรายช่วงที่ผ่านเกณฑ์ โปรดตรวจสอบสภาพปัจจุบัน" : "Structured road-segment evidence passed its gate; verify current conditions.") : (th ? "ไม่มีความเสี่ยงรายช่วงหรือสถานะถนนปัจจุบัน" : "Per-segment risk and current road status are unavailable.")}</p></article>
            </>}

            {displayedTab === "scenario" && <>
              <h3>{th ? "สถานการณ์" : "Scenario"}</h3>
              {activeScenario === "baseline" || !supportsScenarios ? <p className="empty-tab-state">{supportsScenarios ? (th ? "เลือกสถานการณ์ที่ไม่ใช่ค่าฐานเพื่อเปรียบเทียบ" : "Choose a non-baseline scenario to compare.") : (th ? "ยังไม่มีการเปรียบเทียบสถานการณ์ที่ผ่านการทบทวน" : "No reviewed scenario comparison is available.")}</p> : <section className="scenario-evidence-comparison" aria-live="polite"><div className="scenario-evidence-heading"><h3>{activeScenario === "add_temporary_shelter" ? (th ? "ตัวเลือกสถานที่ชั่วคราว" : "Temporary facility option") : (th ? "สถานการณ์ปิดถนน" : "Road-closure scenario")}</h3><StatePill tone={scenarioPresentation.tone === "improves" ? "ready" : scenarioPresentation.tone === "worsens" ? "blocked" : "info"}>{formatServerDelta(scenarioResult.delta)}</StatePill></div><dl><div><dt>{th ? "ค่าฐาน" : "Baseline access loss"}</dt><dd>{formatNumber(baselineScenarioResult.people_losing_30_min_access, language)}</dd></div><div><dt>{th ? "สถานการณ์" : "Scenario access loss"}</dt><dd>{formatNumber(scenarioResult.people_losing_30_min_access, language)}</dd></div><div><dt>{th ? "ผลต่าง" : "Access change"}</dt><dd>{formatServerDelta(scenarioResult.delta)}</dd></div><div><dt>{th ? "ความเสมอภาค ค่าฐาน / สถานการณ์" : "Baseline / scenario equity"}</dt><dd>{formatNumber(baselineScenarioResult.equity_gap_ratio, language, 2)} / {formatNumber(scenarioResult.equity_gap_ratio, language, 2)}</dd></div></dl></section>}
            </>}

            {displayedTab === "verification" && <>
              <div className="tab-heading-row"><div><h3>{th ? "คิวการยืนยัน" : "Verification queue"}</h3><p>{th ? "รายการที่ต้องปิดก่อนยกระดับการใช้หลักฐาน" : "Items to close before stronger evidence use."}</p></div><button type="button" className="secondary-action" onClick={downloadVerificationQueue}>{th ? "ส่งออกคิว" : "Export queue"}</button></div>
              {verificationQueue.length > 0 ? <ol className="verification-queue">{verificationQueue.map((item) => <li key={item.id}><span className={`verification-severity ${item.severity}`}>{item.severity}</span><div><b>{item.title}</b><p>{item.detail}</p></div></li>)}</ol> : <p className="empty-tab-state">{th ? "ไม่มีรายการค้าง" : "No outstanding verification items."}</p>}
            </>}

            {displayedTab === "method" && <>
              <h3>{th ? "ข้อมูลและวิธี" : "Data & method"}</h3>
              <p className="decision-section-label">{th ? "องค์ประกอบคะแนน FPPS" : "FPPS score components"}</p>
              <div className="decision-scores"><ScoreBar label={th ? "โอกาสน้ำท่วม" : "Flood likelihood"} value={selected.flood_likelihood_0_100} /><ScoreBar label={th ? "การสัมผัส" : "Exposure"} value={selected.exposure_0_100} /><ScoreBar label={th ? "ช่องว่างการเข้าถึง" : "Access gap"} value={selected.access_gap_0_100} /><ScoreBar label={th ? "ความสำคัญถนน" : "Road criticality"} value={selected.road_criticality_0_100} /><ScoreBar label={th ? "บริบทความเปราะบาง" : "Vulnerability context"} value={selected.vulnerability_context_0_100} /></div>
              <p className="method-weights"><b>{th ? "น้ำหนักมาตรฐาน" : "Standard weights"}</b> 30 / 25 / 20 / 15 / 10</p>
              <section className="provenance-details command-provenance-card">
                <h3>{th ? "แหล่งที่มา ความเชื่อมั่น และสมมติฐาน" : "Provenance, confidence, assumptions"}</h3>
                <dl>
                  <div><dt>{th ? "แหล่งข้อมูลสรุป" : "Summary source"}</dt><dd>{planningSourceName(selected.source_name)}</dd></div>
                  <div><dt>{th ? "เวลาข้อมูลสรุป" : "Summary source time"}</dt><dd>{formatSourceTime(selected.source_timestamp, language)} ICT</dd></div>
                  <div><dt>{th ? "ความเชื่อมั่น" : "Confidence"}</dt><dd>{formatConfidence(selected.confidence_class, language)}</dd></div>
                  <div><dt>{th ? "รหัสการรันแบบจำลอง" : "Bound model run"}</dt><dd>{data.evidenceContext.model_run_id ?? (th ? "ยังไม่มีการผูกแบบจำลอง" : "No model run bound")}</dd></div>
                  <div><dt>{th ? "แบบจำลองและรุ่น" : "Model and version"}</dt><dd>{data.evidenceRecord?.model_id && data.evidenceRecord.model_version ? `${data.evidenceRecord.model_id} · ${data.evidenceRecord.model_version}` : (th ? "ยังไม่มีการบันทึก" : "Not recorded")}</dd></div>
                </dl>
                <h4>{th ? "องค์ประกอบแหล่งข้อมูลและเวลา" : "Source components and time meaning"}</h4>
                <ul className="command-source-components">
                  {data.evidenceContext.source_components.map((component) => (
                    <li key={component.source_component_id}>
                      <b>{component.source_name}</b>
                      <span><code>{component.role}</code> · {component.source_timestamp ? formatSourceTime(component.source_timestamp, language) : (th ? "ไม่ทราบเวลา" : "Time unknown")}</span>
                      <small>{th ? "ความหมายของเวลา" : "Time meaning"}: <code>{component.temporal_meaning}</code> · {th ? "ความใหม่" : "Freshness"}: <code>{component.freshness}</code></small>
                    </li>
                  ))}
                </ul>
                <ul>{planningAssumptions(selected, language).map((item) => <li key={item}>{item}</li>)}</ul>
              </section>
              <div className="download-actions"><button type="button" onClick={downloadBrief}>{th ? "ดาวน์โหลดสรุปสองภาษา" : "Download bilingual brief"}</button><button className="secondary" type="button" onClick={downloadFilteredGeoJson}>{th ? "ดาวน์โหลด GeoJSON ที่กรอง" : "Download filtered GeoJSON"}</button></div>
              {briefError && <p className="download-error" role="status">{th ? "ไม่สามารถดาวน์โหลดสรุปได้ในขณะนี้ โปรดลองอีกครั้ง" : "The brief is temporarily unavailable. Please try again."}</p>}
            </>}
          </section>
        </aside>

      </div>
    </main>
  );
}

function commandTabLabel(tab: CommandTab, language: "en" | "th"): string {
  const labels: Record<CommandTab, Record<"en" | "th", string>> = {
    summary: { en: "Summary", th: "สรุป" },
    facilities: { en: "Facilities & access", th: "สถานที่และการเข้าถึง" },
    scenario: { en: "Scenario", th: "สถานการณ์" },
    verification: { en: "Verification", th: "การยืนยัน" },
    method: { en: "Data & method", th: "ข้อมูลและวิธี" },
  };
  return labels[tab][language];
}

function commandFacilityOperationLabel(properties: Record<string, unknown>, language: "en" | "th"): string {
  const operation = String(properties.operating_status ?? "").toLowerCase();
  if (["open", "operating", "active"].includes(operation)) return language === "th" ? "เปิดใช้งาน" : "Operating";
  if (["closed", "inactive"].includes(operation)) return language === "th" ? "ปิด" : "Closed";
  return language === "th" ? "ยังไม่ยืนยันการเปิดใช้งาน" : "Current operation not verified";
}

function mergeRoadCollections(
  regional: FeatureCollection,
  detail: { areaId: string; features?: FeatureCollection } | undefined,
  selectedAreaId: string,
): FeatureCollection {
  if (!detail?.features || detail.areaId !== selectedAreaId) return regional;
  return {
    type: "FeatureCollection",
    name: `${regional.name}_with_${selectedAreaId}_detail`,
    features: [
      ...regional.features.filter((feature) => feature.properties.area_id !== selectedAreaId),
      ...detail.features.features,
    ],
  };
}
