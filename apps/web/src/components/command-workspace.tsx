"use client";

import Image from "next/image";
import { useCallback, useEffect, useMemo, useState } from "react";

import { GeoMap } from "@/components/geo-map";
import { LanguageToggle } from "@/components/language-toggle";
import { ScoreBar } from "@/components/score-bar";
import { StatePill } from "@/components/state-pill";
import { rankVisibleAreas, toggleCommandClass } from "@/lib/command-filter";
import { downloadText } from "@/lib/download";
import { formatConfidence, formatNumber, formatSourceTime, formatTopReason } from "@/lib/format";
import { loadMaeSaiRoadDetail } from "@/lib/data-provider";
import { visibleLayerAttributions } from "@/lib/map-attribution";
import { formatServerDelta, scenarioMapPresentation } from "@/lib/scenario-presentation";
import type { AreaRecord, FeatureCollection, ScenarioId } from "@/lib/types";
import { useFloodGuardData } from "@/lib/use-floodguard-data";
import { useLanguage } from "@/lib/use-language";

const ACTION_CLASSES = ["A", "B", "C", "D", "E"] as const;

const ACTION_TEXT = {
  A: { en: "Prepare life-safety resources and verify the area first.", th: "เตรียมทรัพยากรเพื่อความปลอดภัยและตรวจสอบพื้นที่เป็นลำดับแรก" },
  B: { en: "Verify critical links and prepare continuity options.", th: "ตรวจสอบเส้นทางสำคัญและเตรียมทางเลือกเพื่อความต่อเนื่อง" },
  C: { en: "Verify essential-service access and backup arrangements.", th: "ตรวจสอบการเข้าถึงบริการจำเป็นและแผนสำรอง" },
  D: { en: "Prioritize longer-term resilience measures.", th: "จัดลำดับมาตรการเสริมความยืดหยุ่นระยะยาว" },
  E: { en: "Monitor and obtain better evidence before action.", th: "ติดตามและเพิ่มหลักฐานก่อนตัดสินใจ" },
} as const;

function offlineBrief(area: AreaRecord, datasetMode: "fixture_demo" | "candidate" | "official_input"): string {
  const action = ACTION_TEXT[area.action_class as keyof typeof ACTION_TEXT] ?? ACTION_TEXT.E;
  const disclosure = datasetMode === "official_input"
    ? "Verified planning data / ข้อมูลการวางแผนที่ตรวจสอบแล้ว"
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
- Reason / เหตุผล: ${planningSourceName(area.top_reason)} / ${formatTopReason(area.action_class, area.top_reason, "th")}

## Access and equity / การเข้าถึงและความเสมอภาค

- People losing 30-minute access (modelled planning estimate): ${area.people_losing_30_min_access}
- Equity gap ratio: ${area.equity_gap_ratio ?? "unavailable"}
- Method: nearest-facility shortest-path threshold analysis; not capacity-aware 2SFCA.

## Recommended planning action / ข้อเสนอเพื่อการวางแผน

- ${action.en}
- ${action.th}

## Provenance / แหล่งที่มา

- Source: ${planningSourceName(area.source_name)}
- Source timestamp: ${area.source_timestamp}
- Data version: ${planningDataVersion(area.data_version)}
- Assumptions: ${planningAssumptions(area).join("; ")}
`;
}

function planningSourceName(sourceName: string): string {
  return sourceName
    .replace(/\bcandidate\b/gi, "planning")
    .replace(/\bfixture\b/gi, "reference")
    .replace(/\bsynthetic\b/gi, "modelled");
}

function planningDataVersion(dataVersion: string): string {
  return dataVersion
    .replace(/candidate/gi, "planning")
    .replace(/fixture[_-]?demo/gi, "planning")
    .replace(/synthetic/gi, "modelled");
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
  const data = useFloodGuardData("mae_sai_candidate_v1");
  const [language, setLanguage] = useLanguage("en");
  const [selectedId, setSelectedId] = useState("TH570906");
  const [scenario, setScenario] = useState<ScenarioId>("baseline");
  const [activeClasses, setActiveClasses] = useState<Set<string>>(() => new Set(ACTION_CLASSES));
  const [showRoads, setShowRoads] = useState(true);
  const [showFacilities, setShowFacilities] = useState(true);
  const [showAccess, setShowAccess] = useState(true);
  const [selectedRoadDetail, setSelectedRoadDetail] = useState<{ areaId: string; features?: FeatureCollection }>();
  const [evidenceDrawerOpen, setEvidenceDrawerOpen] = useState(true);
  const [briefError, setBriefError] = useState(false);
  const th = language === "th";
  const selected = data.areas.find((area) => area.area_id === selectedId) ?? data.areas[0];
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
    () => mergeRoadCollections(data.roadFeatures, selectedRoadDetail, selectedId),
    [data.roadFeatures, selectedId, selectedRoadDetail],
  );
  const roadDetailState: "bundled" | "loading" | "ready" | "unavailable" = data.dataOrigin !== "api"
    ? "bundled"
    : selectedRoadDetail?.areaId !== selectedId
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
  const scenarioResult = selected.scenario_results[activeScenario];
  const baselineScenarioResult = selected.scenario_results.baseline;
  const scenarioPresentation = scenarioMapPresentation(selected.action_class, activeScenario, scenarioResult);
  const rankedAreas = rankVisibleAreas(data.areas, activeClasses);
  const selectedRank = rankedAreas.findIndex((area) => area.area_id === selected.area_id) + 1;
  const selectedRoadCount = selected.candidate_evidence?.road_count
    ?? effectiveRoadFeatures.features.filter((feature) => feature.properties.area_id === selected.area_id).length;
  const selectedFacilityCount = data.facilityFeatures.features.filter((feature) => feature.properties.area_id === selected.area_id).length;
  const selectedAccessEvidence = data.accessFeatures.features.find((feature) => feature.properties.area_id === selected.area_id);
  const selectArea = useCallback((areaId: string) => setSelectedId(areaId), []);

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
    const visibleIds = new Set(data.areas.filter((area) => activeClasses.has(area.action_class)).map((area) => area.area_id));
    const areaById = new Map(data.areas.map((area) => [area.area_id, area]));
    const filtered = {
      type: data.areaFeatures.type,
      name: "mae_sai_planning_areas",
      features: data.areaFeatures.features
        .filter((feature) => visibleIds.has(String(feature.properties.area_id)))
        .map((feature) => {
          const area = areaById.get(String(feature.properties.area_id));
          return {
            ...feature,
            properties: area ? {
              area_id: area.area_id,
              area_name_en: area.area_name_en,
              area_name_th: area.area_name_th,
              action_class: area.action_class,
              fpps_0_100: area.fpps_0_100,
              confidence_class: area.confidence_class,
              source_timestamp: area.source_timestamp,
              source_name: planningSourceName(area.source_name),
              assumptions: planningAssumptions(area),
            } : {
              area_id: String(feature.properties.area_id),
            },
          };
        }),
    };
    downloadText("floodguard-mae-sai-planning-areas.geojson", JSON.stringify(filtered, null, 2), "application/geo+json");
  };

  const downloadBrief = () => {
    setBriefError(false);
    try {
      downloadText(`floodguard-${selected.area_id}-planning-brief.md`, offlineBrief(selected, data.status.dataset_mode), "text/markdown;charset=utf-8");
    } catch {
      setBriefError(true);
    }
  };

  return (
    <main className="command-page" lang={language}>
      <header className="command-header command-product-header">
        <a href="/command/" className="brand brand-light"><Image src="/icon.svg" alt="" width={40} height={40} priority /><span><b>FloodGuard</b><small>{th ? "ศูนย์บัญชาการเพื่อการวางแผน" : "Planning command center"}</small></span></a>
        <nav aria-label="Product surfaces"><a href="/public/">{th ? "ประชาชน" : "Public"}</a><a className="active" href="/command/">{th ? "บัญชาการ" : "Command"}</a><a href="/studio/">Studio</a></nav>
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
        <h1>{th ? "สรุปศูนย์บัญชาการ" : "Command summary"}</h1>
        <p>{th ? "ใช้หน้าจอแท็บเล็ตหรือเดสก์ท็อปเพื่อดูแผนที่และแผงควบคุมทั้งหมด" : "Use a tablet or desktop for the full map and control workspace."}</p>
        <dl><div><dt>{th ? "พื้นที่" : "Area"}</dt><dd>{th ? selected.area_name_th : selected.area_name_en}</dd></div><div><dt>FPPS</dt><dd>{selected.fpps_0_100.toFixed(1)} / {selected.action_class}</dd></div></dl>
      </div>

      <div className="command-workspace command-dashboard-grid">
        <aside className="control-rail command-control-panel" aria-label={th ? "ตัวควบคุม" : "Controls"}>
          <div className="rail-section">
            <p className="rail-label">{th ? "พื้นที่รายงาน" : "Reporting area"}</p>
            <select value={selected.area_id} onChange={(event) => setSelectedId(event.target.value)} aria-label={th ? "เลือกพื้นที่รายงาน" : "Select reporting area"}>
              {data.areas.map((area) => <option value={area.area_id} key={area.area_id}>{area.area_id} · {th ? "ชั้น" : "Class"} {area.action_class}</option>)}
            </select>
          </div>
          <section className="rail-section ranked-areas" aria-labelledby="ranked-areas-title">
            <div className="rail-section-heading"><p className="rail-label" id="ranked-areas-title">{th ? "ลำดับ FPPS" : "FPPS ranking"}</p><span>{rankedAreas.length}/{data.areas.length}</span></div>
            <ol>
              {rankedAreas.map((area, index) => (
                <li key={area.area_id}>
                  <button type="button" className={area.area_id === selected.area_id ? "selected" : ""} aria-current={area.area_id === selected.area_id ? "true" : undefined} onClick={() => selectArea(area.area_id)}>
                    <span className="rank-number">{String(index + 1).padStart(2, "0")}</span>
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
          <fieldset className="rail-section class-filters"><legend>{th ? "กรองชั้น A–E" : "A–E filters"}</legend><div>{ACTION_CLASSES.map((actionClass) => <button type="button" aria-pressed={activeClasses.has(actionClass)} className={activeClasses.has(actionClass) ? `active class-${actionClass.toLowerCase()}` : ""} key={actionClass} onClick={() => toggleClass(actionClass)}>{actionClass}</button>)}</div></fieldset>
          <fieldset className="rail-section layer-toggles"><legend>{th ? "ชั้นข้อมูล" : "Layers"}</legend><label><input type="checkbox" checked readOnly /> {th ? "พื้นที่ FPPS" : "FPPS areas"}</label><label className={roadLayerAvailable ? undefined : "disabled"}><input type="checkbox" checked={roadLayerAvailable && showRoads} disabled={!roadLayerAvailable} onChange={(event) => setShowRoads(event.target.checked)} /> {roadLayerAvailable ? (th ? `ความเสี่ยงถนน (${totalRoadCount.toLocaleString()})` : `Road risk (${totalRoadCount.toLocaleString()})`) : (th ? "ความเสี่ยงถนน (ไม่มี)" : "Road risk (unavailable)")}</label><label className={facilityLayerAvailable ? undefined : "disabled"}><input type="checkbox" checked={facilityLayerAvailable && showFacilities} disabled={!facilityLayerAvailable} onChange={(event) => setShowFacilities(event.target.checked)} /> {facilityLayerAvailable ? (th ? `สถานที่สำคัญ (${data.facilityFeatures.features.length})` : `Important facilities (${data.facilityFeatures.features.length})`) : (th ? "สถานที่สำคัญ (ไม่มี)" : "Important facilities (unavailable)")}</label><label className={accessLayerAvailable ? undefined : "disabled"}><input type="checkbox" checked={accessLayerAvailable && showAccess} disabled={!accessLayerAvailable} onChange={(event) => setShowAccess(event.target.checked)} /> {accessLayerAvailable ? (th ? "หลักฐานการเข้าถึง" : "Access evidence") : (th ? "หลักฐานการเข้าถึง (ไม่มี)" : "Access evidence (unavailable)")}</label></fieldset>
          <div className="rail-section locked-policy"><p className="rail-label">{th ? "น้ำหนัก FPPS มาตรฐาน" : "Standard FPPS weights"}</p><b>30 / 25 / 20 / 15 / 10</b><p>{th ? "การเปรียบเทียบสถานการณ์ไม่เปลี่ยนน้ำหนักเหล่านี้" : "Scenario comparisons do not alter these weights."}</p></div>
          <section className="rail-section planning-safeguard" aria-labelledby="planning-safeguard-title">
            <p className="rail-label" id="planning-safeguard-title">{th ? "การยืนยันก่อนดำเนินการ" : "Before action"}</p>
            <p>{th ? "ตรวจสอบสภาพถนน บทบาทและความจุสถานที่ รวมถึงคำแนะนำจาก ปภ. และหน่วยงานท้องถิ่น" : "Verify road conditions, facility role and capacity, and current DDPM or local-authority instructions."}</p>
          </section>
        </aside>

        <section className="map-workspace command-map-panel" aria-label={th ? "พื้นที่ทำงานแผนที่" : "Map workspace"}>
          <div className="map-workspace-heading"><div><p className="eyebrow">{th ? "พื้นที่ทำงานหลัก" : "Primary workspace"}</p><h1>{th ? selected.area_name_th : selected.area_name_en}</h1></div><span>{selectedRank > 0 ? `#${selectedRank} FPPS` : "—"} · {th ? "เลือกพื้นที่เพื่อซิงค์หลักฐาน" : "select an area to synchronize evidence"}</span></div>
          <GeoMap areas={data.areas} selectedId={selected.area_id} onSelect={selectArea} language={language} showRoads={roadLayerAvailable && showRoads} showFacilities={facilityLayerAvailable && showFacilities} showAccess={accessLayerAvailable && showAccess} classFilter={activeClasses} height="100%" areaFeatures={data.areaFeatures} roadFeatures={effectiveRoadFeatures} regionalRoadCount={data.roadFeatures.features.length} roadDatasetTotal={totalRoadCount} roadDetailState={roadDetailState} facilityFeatures={data.facilityFeatures} accessFeatures={data.accessFeatures} contextFeatures={data.contextFeatures} datasetMode={data.status.dataset_mode} scenarioId={activeScenario} showSelectionSheet={false} attributions={mapAttributions} visualPalette="public-blue" enableBasemaps />
          {supportsScenarios ? <div className="scenario-delta-strip" aria-live="polite" data-scenario-tone={scenarioPresentation.tone}><span>{activeScenario === "baseline" ? (th ? "ค่าฐาน" : "Baseline") : activeScenario === "add_temporary_shelter" ? (th ? "ตัวเลือกสถานที่ชั่วคราว" : "Temporary facility option") : (th ? "สถานการณ์ปิดถนน" : "Road-closure scenario")}</span><b>{formatNumber(scenarioResult.people_losing_30_min_access, language)} {th ? "คนสูญเสียการเข้าถึง 30 นาที" : "people lose 30-min access"}</b><strong className={scenarioPresentation.tone}>{formatServerDelta(scenarioResult.delta)} {th ? "เทียบค่าฐาน" : "vs baseline"}</strong></div> : <div className="scenario-delta-strip current-outlook-strip" aria-live="polite" data-scenario-tone="unavailable"><span>{th ? "ภาพรวมปัจจุบัน" : "Current planning outlook"}</span><b>{formatNumber(scenarioResult.people_losing_30_min_access, language)} {th ? "คนสูญเสียการเข้าถึง 30 นาทีเชิงแบบจำลอง" : "modelled 30-min access loss"}</b><strong>{th ? "ไม่มีการเปรียบเทียบสถานการณ์" : "Scenario comparison unavailable"}</strong></div>}
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

        <aside className="decision-panel command-insight-panel" aria-label={th ? "หลักฐานการตัดสินใจ" : "Decision evidence"} data-scenario-id={activeScenario} data-scenario-tone={scenarioPresentation.tone}>
          <div className="decision-title" aria-live="polite"><div><p className="eyebrow">{th ? "หลักฐานพื้นที่" : "Area evidence"} · {selected.area_id}</p><h2>{th ? selected.area_name_th : selected.area_name_en}</h2><StatePill tone="caution">{formatConfidence(selected.confidence_class, language)} {th ? "ความเชื่อมั่น" : "confidence"}</StatePill></div><span className={`decision-class class-${selected.action_class.toLowerCase()}`} aria-label={`${th ? "ชั้น" : "Class"} ${selected.action_class}`}>{selected.action_class}</span></div>
          <div className="fpps-block"><span>FPPS</span><b>{selected.fpps_0_100.toFixed(1)}</b><small>/ 100</small></div>
          <p className="top-reason">{formatTopReason(selected.action_class, selected.top_reason, language)}</p>
          <dl className="evidence-grid"><div><dt>{th ? "สูญเสียการเข้าถึง 30 นาที · แบบจำลอง" : "30-min access loss · modelled"}</dt><dd>{formatNumber(scenarioResult.people_losing_30_min_access, language)}</dd></div><div><dt>{th ? "อัตราช่องว่างความเสมอภาค · แบบจำลอง" : "Equity-gap ratio · modelled"}</dt><dd>{formatNumber(scenarioResult.equity_gap_ratio, language, 2)}</dd></div><div><dt>{th ? "ช่วงถนนที่วิเคราะห์" : "Road segments analysed"}</dt><dd>{roadLayerAvailable ? selectedRoadCount.toLocaleString() : (th ? "ไม่มีข้อมูล" : "Unavailable")}</dd></div><div><dt>{th ? "สถานที่สำคัญ" : "Important facilities"}</dt><dd>{facilityLayerAvailable ? `${selectedFacilityCount} ${th ? "แห่ง · ต้องยืนยันในพื้นที่" : "mapped · confirm locally"}` : (th ? "ไม่มีข้อมูล" : "Unavailable")}</dd></div><div><dt>{th ? "สะพานที่ติดแท็ก" : "Bridge-tagged ways"}</dt><dd>{selected.candidate_evidence?.bridge_count ?? (th ? "ไม่มีข้อมูล" : "Unavailable")}</dd></div><div><dt>{th ? "จุดหลักฐานการเข้าถึง" : "Access-evidence point"}</dt><dd>{selectedAccessEvidence ? (th ? "มี · แบบจำลอง" : "Present · modelled") : (th ? "ไม่มีข้อมูล" : "Unavailable")}</dd></div></dl>
          {supportsScenarios ? <section className="scenario-evidence-comparison" aria-labelledby="scenario-evidence-title" aria-live="polite">
            <div className="scenario-evidence-heading"><div><p className="eyebrow">{th ? "การเปรียบเทียบสถานการณ์" : "Scenario comparison"}</p><h3 id="scenario-evidence-title">{activeScenario === "baseline" ? (th ? "ค่าฐาน" : "Baseline") : activeScenario === "add_temporary_shelter" ? (th ? "ตัวเลือกสถานที่ชั่วคราว" : "Temporary facility option") : (th ? "สถานการณ์ปิดถนน" : "Road-closure scenario")}</h3></div><StatePill tone={scenarioPresentation.tone === "improves" ? "ready" : scenarioPresentation.tone === "worsens" ? "blocked" : "info"}>{formatServerDelta(scenarioResult.delta)} {th ? "การเข้าถึง" : "access"}</StatePill></div>
            <dl>
              <div><dt>{th ? "ค่าฐาน: สูญเสียการเข้าถึง" : "Baseline access loss"}</dt><dd>{formatNumber(baselineScenarioResult.people_losing_30_min_access, language)}</dd></div>
              <div><dt>{th ? "สถานการณ์: สูญเสียการเข้าถึง" : "Scenario access loss"}</dt><dd>{formatNumber(scenarioResult.people_losing_30_min_access, language)}</dd></div>
              <div><dt>{th ? "ผลต่างการเข้าถึง" : "Access change"}</dt><dd className={`scenario-${scenarioPresentation.tone}`}>{formatServerDelta(scenarioResult.delta)}</dd></div>
              <div><dt>{th ? "ความเสมอภาคค่าฐาน / สถานการณ์" : "Baseline / scenario equity"}</dt><dd>{formatNumber(baselineScenarioResult.equity_gap_ratio, language, 2)} / {formatNumber(scenarioResult.equity_gap_ratio, language, 2)}</dd></div>
            </dl>
            <p>{th ? "ค่าประมาณสถานการณ์ใช้ข้อมูลการวางแผนที่เผยแพร่ในมุมมองนี้" : "Scenario estimates use the planning evidence published in this view."}</p>
          </section> : <section className="scenario-evidence-comparison planning-evidence-boundary" aria-labelledby="scenario-evidence-title" aria-live="polite">
            <div className="scenario-evidence-heading"><div><p className="eyebrow">{th ? "ขอบเขตหลักฐานการวางแผน" : "Planning evidence boundary"}</p><h3 id="scenario-evidence-title">{th ? "ภาพรวมปัจจุบัน" : "Current planning outlook"}</h3></div><StatePill tone="caution">{th ? "ต้องตรวจสอบ" : "Review required"}</StatePill></div>
            <p>{th ? "การเปรียบเทียบสถานการณ์จะเพิ่มได้เมื่อการทบทวนหลักฐานสนับสนุนเสร็จสมบูรณ์ มุมมองนี้เน้นตัวชี้วัดการวางแผนที่เผยแพร่" : "Scenario comparison can be added after its supporting evidence review is complete. This view focuses on the published planning indicators."}</p>
            <p><b>{th ? "สถานที่:" : "Facilities:"}</b> {th ? "พิกัดมาจากข้อมูลเปิด โปรดยืนยันบทบาทฉุกเฉิน การเปิดใช้งาน ความจุ และการเข้าถึงกับหน่วยงานท้องถิ่น" : "Coordinates come from open data; confirm emergency role, current operation, capacity, and accessibility locally."}</p>
            <p><b>{th ? "ถนน:" : "Roads:"}</b> {th ? "ผลกระทบเป็นค่าประมาณเชิงแบบจำลอง โปรดตรวจสอบสภาพปัจจุบันในพื้นที่ เนื่องจากไม่ยืนยันการปิดถนน" : "Impacts are modelled estimates. Check current field conditions because they do not confirm a road closure."}</p>
          </section>}
          <p className="decision-section-label">{th ? "องค์ประกอบคะแนน FPPS" : "FPPS score components"}</p>
          <div className="decision-scores">
            <ScoreBar label={th ? "โอกาสน้ำท่วม" : "Flood likelihood"} value={selected.flood_likelihood_0_100} />
            <ScoreBar label={th ? "การสัมผัส" : "Exposure"} value={selected.exposure_0_100} />
            <ScoreBar label={th ? "ช่องว่างการเข้าถึง" : "Access gap"} value={selected.access_gap_0_100} />
            <ScoreBar label={th ? "ความสำคัญถนน" : "Road criticality"} value={selected.road_criticality_0_100} />
            <ScoreBar label={th ? "บริบทความเปราะบาง" : "Vulnerability context"} value={selected.vulnerability_context_0_100} />
          </div>
          <article className="recommended-action"><p className="eyebrow">{th ? "ข้อเสนอเพื่อการวางแผน" : "Planning action"}</p><p>{ACTION_TEXT[selected.action_class as keyof typeof ACTION_TEXT]?.[language] ?? ACTION_TEXT.E[language]}</p></article>
          <section className="provenance-details command-provenance-card" aria-labelledby="provenance-title"><h3 id="provenance-title">{th ? "แหล่งที่มา ความเชื่อมั่น และสมมติฐาน" : "Provenance, confidence, assumptions"}</h3><dl><div><dt>{th ? "แหล่งข้อมูล" : "Source"}</dt><dd>{planningSourceName(selected.source_name)}</dd></div><div><dt>{th ? "เวลาข้อมูล" : "Source time"}</dt><dd>{formatSourceTime(selected.source_timestamp, language)} ICT</dd></div><div><dt>{th ? "ความเชื่อมั่น" : "Confidence"}</dt><dd>{formatConfidence(selected.confidence_class, language)}</dd></div>{selected.candidate_evidence && <><div><dt>{th ? "ขอบเขต" : "Boundary"}</dt><dd>{selected.candidate_evidence.boundary_version} · {selected.candidate_evidence.boundary_valid_on}</dd></div><div><dt>{th ? "อ้างอิงน้ำท่วม" : "Flood reference"}</dt><dd>{th ? "ข้อมูลอ้างอิงข้ามพรมแดนเพื่อบริบทการวางแผน" : "Cross-border reference for planning context"}</dd></div><div><dt>{th ? "ความครอบคลุม" : "Coverage"}</dt><dd>WorldPop {(selected.candidate_evidence.worldpop_bbox_coverage_rate * 100).toFixed(1)}% · road snap {(selected.candidate_evidence.road_snap_population_coverage_rate * 100).toFixed(1)}% · DEM {(selected.candidate_evidence.dem_population_coverage_rate * 100).toFixed(1)}%</dd></div></>}</dl><div className="decision-eligibility-row planning-use-row"><span><b>{th ? "การนำไปใช้" : "Intended use"}</b><strong>{th ? "จัดลำดับการเตรียมพร้อม" : "Preparedness prioritization"}</strong></span><span><b>{th ? "ขั้นตอนถัดไป" : "Next step"}</b><strong>{th ? "ยืนยันในพื้นที่" : "Confirm locally"}</strong></span></div><p className="decision-eligibility-reason planning-use-guidance"><b>{th ? "ก่อนดำเนินการ:" : "Before action:"}</b> {th ? "ตรวจสอบสภาพปัจจุบันและคำแนะนำกับ ปภ. และหน่วยงานท้องถิ่น" : "Check current conditions and instructions with DDPM and local authorities."}</p><ul>{planningAssumptions(selected, language).map((item) => <li key={item}>{item}</li>)}</ul></section>
          <div className="download-actions"><button type="button" onClick={downloadBrief}>{th ? "ดาวน์โหลดสรุปสองภาษา" : "Download bilingual brief"}</button><button className="secondary" type="button" onClick={downloadFilteredGeoJson}>{th ? "ดาวน์โหลด GeoJSON ที่กรอง" : "Download filtered GeoJSON"}</button></div>
          {briefError && <p className="download-error" role="status">{th ? "ไม่สามารถดาวน์โหลดสรุปได้ในขณะนี้ โปรดลองอีกครั้ง" : "The brief is temporarily unavailable. Please try again."}</p>}
        </aside>
      </div>
    </main>
  );
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
