"use client";

import Image from "next/image";
import { useCallback, useState } from "react";

import { GeoMap } from "@/components/geo-map";
import { LanguageToggle } from "@/components/language-toggle";
import { ScoreBar } from "@/components/score-bar";
import { StatusBar } from "@/components/status-bar";
import { toggleCommandClass } from "@/lib/command-filter";
import { downloadText } from "@/lib/download";
import { formatConfidence, formatNumber, formatTopReason } from "@/lib/format";
import { loadApiBrief } from "@/lib/data-provider";
import type { AreaRecord, Language, ScenarioId } from "@/lib/types";
import { useFloodGuardData } from "@/lib/use-floodguard-data";

const ACTION_CLASSES = ["A", "B", "C", "D", "E"] as const;

const ACTION_TEXT = {
  A: { en: "Prepare life-safety resources and verify the area first.", th: "เตรียมทรัพยากรเพื่อความปลอดภัยและตรวจสอบพื้นที่เป็นลำดับแรก" },
  B: { en: "Verify critical links and prepare continuity options.", th: "ตรวจสอบเส้นทางสำคัญและเตรียมทางเลือกเพื่อความต่อเนื่อง" },
  C: { en: "Verify essential-service access and backup arrangements.", th: "ตรวจสอบการเข้าถึงบริการจำเป็นและแผนสำรอง" },
  D: { en: "Prioritize longer-term resilience measures.", th: "จัดลำดับมาตรการเสริมความยืดหยุ่นระยะยาว" },
  E: { en: "Monitor and obtain better evidence before action.", th: "ติดตามและเพิ่มหลักฐานก่อนตัดสินใจ" },
} as const;

function offlineBrief(area: AreaRecord): string {
  const action = ACTION_TEXT[area.action_class as keyof typeof ACTION_TEXT] ?? ACTION_TEXT.E;
  return `# FloodGuard bilingual action brief / เอกสารสรุปการดำเนินการสองภาษา

Fixture demo / ชุดข้อมูลสาธิต — Non-operational / ไม่ใช่ระบบปฏิบัติการ — Not an official warning / ไม่ใช่ประกาศเตือนภัยอย่างเป็นทางการ

## Area / พื้นที่

- ${area.area_name_en}
- ${area.area_name_th}
- ID: ${area.area_id}

## Priority / ลำดับความสำคัญ

- FPPS: ${area.fpps_0_100.toFixed(2)}
- Action class / ชั้นการดำเนินการ: ${area.action_class}
- Confidence / ความเชื่อมั่น: ${area.confidence_class} / ${formatConfidence(area.confidence_class, "th")}
- Reason / เหตุผล: ${area.top_reason} / ${formatTopReason(area.action_class, area.top_reason, "th")}

## Access and equity / การเข้าถึงและความเสมอภาค

- People losing 30-minute access (fixture): ${area.people_losing_30_min_access}
- Equity gap ratio: ${area.equity_gap_ratio ?? "unavailable"}
- Method: nearest-facility shortest-path threshold analysis; not capacity-aware 2SFCA.

## Recommended planning action / ข้อเสนอเพื่อการวางแผน

- ${action.en}
- ${action.th}

## Provenance / แหล่งที่มา

- Source: ${area.source_name}
- Source timestamp: ${area.source_timestamp}
- Data version: ${area.data_version}
- Assumptions: ${area.assumptions.join("; ")}
`;
}

export function CommandWorkspace() {
  const data = useFloodGuardData();
  const [language, setLanguage] = useState<Language>("en");
  const [selectedId, setSelectedId] = useState("FG-TB-002");
  const [scenario, setScenario] = useState<ScenarioId>("baseline");
  const [activeClasses, setActiveClasses] = useState<Set<string>>(() => new Set(ACTION_CLASSES));
  const [showRoads, setShowRoads] = useState(true);
  const [briefError, setBriefError] = useState<string>();
  const th = language === "th";
  const selected = data.areas.find((area) => area.area_id === selectedId) ?? data.areas[0];
  const supportsScenarios = data.scenarioState === "ready" && data.status.dataset_mode === "fixture_demo" && data.status.study_area === "fixture_thailand_demo" && data.status.data_state === "ready";
  const roadLayerAvailable = data.layers.some((layer) => layer.layer_id === "road_risk" && layer.data_state === "ready") && data.roadFeatures.features.length > 0;
  const activeScenario: ScenarioId = supportsScenarios ? scenario : "baseline";
  const scenarioResult = selected.scenario_results[activeScenario];
  const selectArea = useCallback((areaId: string) => setSelectedId(areaId), []);

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
    const filtered = { ...data.areaFeatures, features: data.areaFeatures.features.filter((feature) => visibleIds.has(String(feature.properties.area_id))) };
    downloadText(`floodguard-${data.status.dataset_mode}-filtered.geojson`, JSON.stringify(filtered, null, 2), "application/geo+json");
  };

  const downloadBrief = async () => {
    setBriefError(undefined);
    try {
      if (data.dataOrigin === "api" && data.apiBase) {
        const brief = await loadApiBrief(data.apiBase, selected.area_id);
        downloadText(brief.fileName, brief.contentMarkdown, "text/markdown;charset=utf-8");
        return;
      }
      downloadText(`floodguard-${selected.area_id}-brief.md`, offlineBrief(selected), "text/markdown;charset=utf-8");
    } catch (error) {
      setBriefError(error instanceof Error ? error.message : "Brief download is unavailable.");
    }
  };

  return (
    <main className="command-page" lang={language}>
      <header className="command-header">
        <a href="/command/" className="brand brand-light"><Image src="/icon.svg" alt="" width={40} height={40} priority /><span><b>FloodGuard</b><small>{th ? "ศูนย์บัญชาการเพื่อการวางแผน" : "Planning command center"}</small></span></a>
        <nav aria-label="Product surfaces"><a href="/public/">{th ? "ประชาชน" : "Public"}</a><a className="active" href="/command/">{th ? "บัญชาการ" : "Command"}</a><a href="/studio/">Studio</a></nav>
        <LanguageToggle language={language} onChange={setLanguage} />
      </header>
      <StatusBar data={data} language={language} compact />

      <div className="small-screen-command-note card">
        <h1>{th ? "สรุปศูนย์บัญชาการ" : "Command summary"}</h1>
        <p>{th ? "ใช้หน้าจอแท็บเล็ตหรือเดสก์ท็อปเพื่อดูแผนที่และแผงควบคุมทั้งหมด" : "Use a tablet or desktop for the full map and control workspace."}</p>
        <dl><div><dt>{th ? "พื้นที่" : "Area"}</dt><dd>{th ? selected.area_name_th : selected.area_name_en}</dd></div><div><dt>FPPS</dt><dd>{selected.fpps_0_100.toFixed(1)} / {selected.action_class}</dd></div></dl>
      </div>

      <div className="command-workspace">
        <aside className="control-rail" aria-label={th ? "ตัวควบคุม" : "Controls"}>
          <div className="rail-section">
            <p className="rail-label">{th ? "พื้นที่ศึกษา" : "Study area"}</p>
            <select value={selected.area_id} onChange={(event) => setSelectedId(event.target.value)} aria-label={th ? "เลือกพื้นที่" : "Select area"}>
              {data.areas.map((area) => <option value={area.area_id} key={area.area_id}>{area.area_id} · {th ? "ชั้น" : "Class"} {area.action_class}</option>)}
            </select>
          </div>
          <div className="rail-section">
            <p className="rail-label">{th ? "สถานการณ์จำลองที่เอนจินคำนวณไว้" : "Engine-computed scenario"}</p>
            <select value={activeScenario} disabled={!supportsScenarios} onChange={(event) => setScenario(event.target.value as ScenarioId)} aria-label={th ? "เลือกสถานการณ์" : "Select scenario"}>
              <option value="baseline">{th ? "ค่าฐาน" : "Baseline"}</option>
              {supportsScenarios && <option value="add_temporary_shelter">{th ? "เพิ่มที่พักพิงชั่วคราว" : "Temporary shelter"}</option>}
              {supportsScenarios && <option value="close_road">{th ? "ทดสอบถนนปิด" : "Road-closure stress"}</option>}
            </select>
            <p className="rail-help">{supportsScenarios ? (th ? "ค่ามาจากเอาต์พุตสถานการณ์ของ Python ไม่มีสูตรในเบราว์เซอร์" : "Values come from Python scenario artifacts; there is no browser formula.") : (th ? "ไม่มีสถานการณ์จำลองที่เซิร์ฟเวอร์กำหนดไว้สำหรับชุดข้อมูลนี้" : "No server-defined scenarios are available for this dataset.")}</p>
          </div>
          <fieldset className="rail-section class-filters"><legend>{th ? "กรองชั้น A–E" : "A–E filters"}</legend><div>{ACTION_CLASSES.map((actionClass) => <button type="button" aria-pressed={activeClasses.has(actionClass)} className={activeClasses.has(actionClass) ? `active class-${actionClass.toLowerCase()}` : ""} key={actionClass} onClick={() => toggleClass(actionClass)}>{actionClass}</button>)}</div></fieldset>
          <fieldset className="rail-section layer-toggles"><legend>{th ? "ชั้นข้อมูล" : "Layers"}</legend><label><input type="checkbox" checked readOnly /> {th ? "พื้นที่ FPPS" : "FPPS areas"}</label><label className={roadLayerAvailable ? undefined : "disabled"}><input type="checkbox" checked={roadLayerAvailable && showRoads} disabled={!roadLayerAvailable} onChange={(event) => setShowRoads(event.target.checked)} /> {roadLayerAvailable ? (th ? "ความเสี่ยงถนน" : "Road risk") : (th ? "ความเสี่ยงถนน (ไม่มี)" : "Road risk (unavailable)")}</label><label className="disabled"><input type="checkbox" disabled /> {th ? "ความน่าจะเป็นน้ำท่วม (ไม่มี)" : "Flood probability (unavailable)"}</label></fieldset>
          <div className="rail-section locked-policy"><p className="rail-label">{th ? "นโยบายน้ำหนัก" : "Weight policy"}</p><b>30 / 25 / 20 / 15 / 10</b><p>{th ? "ล็อกตามสัญญาเดิม การวิเคราะห์ความไวแยกจากสถานการณ์" : "Locked to the existing contract. Sensitivity is separate from scenarios."}</p></div>
        </aside>

        <section className="map-workspace" aria-label={th ? "พื้นที่ทำงานแผนที่" : "Map workspace"}>
          <div className="map-workspace-heading"><div><p className="eyebrow">{th ? "พื้นที่ทำงานหลัก" : "Primary workspace"}</p><h1>{th ? selected.area_name_th : selected.area_name_en}</h1></div><span>{th ? "เลือกพื้นที่บนแผนที่เพื่อซิงค์หลักฐาน" : "Select a polygon to synchronize evidence"}</span></div>
          <GeoMap areas={data.areas} selectedId={selected.area_id} onSelect={selectArea} language={language} showRoads={roadLayerAvailable && showRoads} classFilter={activeClasses} height="100%" areaFeatures={data.areaFeatures} roadFeatures={data.roadFeatures} datasetMode={data.status.dataset_mode} />
          <div className="scenario-delta-strip" aria-live="polite"><span>{activeScenario === "baseline" ? (th ? "ค่าฐาน" : "Baseline") : activeScenario === "add_temporary_shelter" ? (th ? "ที่พักพิงชั่วคราว" : "Temporary shelter") : (th ? "ทดสอบถนนปิด" : "Road-closure stress")}</span><b>{formatNumber(scenarioResult.people_losing_30_min_access, language)} {th ? "คนสูญเสียการเข้าถึง 30 นาที" : "people lose 30-min access"}</b><strong className={scenarioResult.delta < 0 ? "improves" : scenarioResult.delta > 0 ? "worsens" : "neutral"}>{scenarioResult.delta > 0 ? "+" : ""}{scenarioResult.delta} {th ? "เทียบค่าฐาน" : "vs baseline"}</strong></div>
        </section>

        <aside className="decision-panel" aria-label={th ? "หลักฐานการตัดสินใจ" : "Decision evidence"}>
          <div className="decision-title"><div><p className="eyebrow">{selected.area_id}</p><h2>{th ? selected.area_name_th : selected.area_name_en}</h2></div><span className={`decision-class class-${selected.action_class.toLowerCase()}`}>{selected.action_class}</span></div>
          <div className="fpps-block"><span>FPPS</span><b>{selected.fpps_0_100.toFixed(1)}</b><small>/ 100</small></div>
          <p className="top-reason">{formatTopReason(selected.action_class, selected.top_reason, language)}</p>
          <div className="decision-scores">
            <ScoreBar label={th ? "โอกาสน้ำท่วม" : "Flood likelihood"} value={selected.flood_likelihood_0_100} />
            <ScoreBar label={th ? "การสัมผัส" : "Exposure"} value={selected.exposure_0_100} />
            <ScoreBar label={th ? "ช่องว่างการเข้าถึง" : "Access gap"} value={selected.access_gap_0_100} />
            <ScoreBar label={th ? "ความสำคัญถนน" : "Road criticality"} value={selected.road_criticality_0_100} />
            <ScoreBar label={th ? "บริบทความเปราะบาง" : "Vulnerability context"} value={selected.vulnerability_context_0_100} />
          </div>
          <dl className="evidence-grid"><div><dt>{th ? "สูญเสียการเข้าถึง 30 นาที" : "30-min access loss"}</dt><dd>{formatNumber(selected.people_losing_30_min_access, language)}</dd></div><div><dt>{th ? "อัตราช่องว่างความเสมอภาค" : "Equity-gap ratio"}</dt><dd>{formatNumber(selected.equity_gap_ratio, language, 2)}</dd></div><div><dt>{th ? "หลักฐานถนน" : "Road evidence"}</dt><dd>{roadLayerAvailable ? `${data.roadFeatures.features.filter((feature) => feature.properties.area_id === selected.area_id).length} ${th ? "ช่วง (แบบจำลอง)" : "modelled segment(s)"}` : (th ? "ไม่มีข้อมูล" : "Unavailable")}</dd></div><div><dt>{th ? "สถานะสถานที่" : "Facility evidence"}</dt><dd>{th ? "ไม่ได้ยืนยัน" : "Unconfirmed"}</dd></div></dl>
          <article className="recommended-action"><p className="eyebrow">{th ? "ข้อเสนอเพื่อการวางแผน" : "Planning action"}</p><p>{ACTION_TEXT[selected.action_class as keyof typeof ACTION_TEXT]?.[language] ?? ACTION_TEXT.E[language]}</p></article>
          <details className="provenance-details"><summary>{th ? "แหล่งที่มา ความเชื่อมั่น และสมมติฐาน" : "Provenance, confidence, assumptions"}</summary><dl><div><dt>{th ? "แหล่งข้อมูล" : "Source"}</dt><dd>{selected.source_name}</dd></div><div><dt>{th ? "เวลาข้อมูล" : "Source time"}</dt><dd>{selected.source_timestamp}</dd></div><div><dt>{th ? "ความเชื่อมั่น" : "Confidence"}</dt><dd>{formatConfidence(selected.confidence_class, language)}</dd></div></dl><ul>{selected.assumptions.map((item) => <li key={item}>{item}</li>)}</ul></details>
          <div className="download-actions"><button type="button" onClick={() => void downloadBrief()}>{th ? "ดาวน์โหลดสรุปสองภาษา" : "Download bilingual brief"}</button><button className="secondary" type="button" onClick={downloadFilteredGeoJson}>{th ? "ดาวน์โหลด GeoJSON ที่กรอง" : "Download filtered GeoJSON"}</button></div>
          {briefError && <p className="download-error" role="status">{th ? "ไม่สามารถดาวน์โหลดสรุปได้: " : "Brief download unavailable: "}{briefError}</p>}
        </aside>
      </div>
    </main>
  );
}
