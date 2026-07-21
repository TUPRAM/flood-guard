"use client";

import type { CSSProperties } from "react";
import { useEffect, useRef, useState } from "react";

import { EvidenceNotice } from "@/components/evidence-notice";
import { GeoMap } from "@/components/geo-map";
import { HouseholdPlanBuilder } from "@/components/household-plan-builder";
import { LanguageToggle } from "@/components/language-toggle";
import { formatConfidence, formatNumber, formatSourceTime, formatTopReason } from "@/lib/format";
import { visibleLayerAttributions } from "@/lib/map-attribution";
import { useFloodGuardData } from "@/lib/use-floodguard-data";
import { useHouseholdPlan } from "@/lib/use-household-plan";
import { useLanguage } from "@/lib/use-language";

type PublicTab = "home" | "map" | "shelters" | "prepare" | "data";

const TAB_LABELS: Record<PublicTab, { th: string; en: string; icon: string }> = {
  home: { th: "หน้าแรก", en: "Home", icon: "home" },
  map: { th: "แผนที่", en: "Map", icon: "map" },
  shelters: { th: "ที่พักพิง", en: "Shelters", icon: "shelters" },
  prepare: { th: "เตรียมพร้อม", en: "Prepare", icon: "prepare" },
  data: { th: "ข้อมูล", en: "Data", icon: "data" },
};

const PUBLIC_DATA_STATE_LABELS = {
  loading: { th: "กำลังตรวจสอบข้อมูลล่าสุด", en: "Checking for updates" },
  ready: { th: "ข้อมูลการวางแผนพร้อม", en: "Planning data available" },
  stale: { th: "โปรดยืนยันข้อมูลล่าสุด", en: "Confirm latest conditions" },
  stale_offline: { th: "ใช้ข้อมูลที่บันทึกล่าสุด", en: "Using latest saved data" },
  blocked: { th: "การอัปเดตยังไม่พร้อม", en: "Updates not yet available" },
  unavailable: { th: "การอัปเดตไม่พร้อมใช้", en: "Updates unavailable" },
} as const;

const PUBLIC_VISIBLE_LAYER_IDS = new Set(["priority_areas", "facilities"]);

type PublicIconName = PublicTab | "change";

function PublicBrandMark() {
  return (
    <svg className="public-brand-mark" viewBox="0 0 44 44" aria-hidden="true">
      <defs>
        <linearGradient id="public-brand-gradient" x1="5" y1="3" x2="39" y2="42" gradientUnits="userSpaceOnUse">
          <stop stopColor="#3182BD" />
          <stop offset="1" stopColor="#08519C" />
        </linearGradient>
      </defs>
      <rect width="44" height="44" rx="13" fill="url(#public-brand-gradient)" />
      <path d="M22 8.5 33 12.4v8.1c0 7.5-4.3 12.5-11 15.4-6.7-2.9-11-7.9-11-15.4v-8.1L22 8.5Z" fill="#fff" />
      <path d="M15.7 18.2c2.2 0 2.2-1.5 4.4-1.5s2.2 1.5 4.4 1.5 2.2-1.5 4.4-1.5M15.7 23c2.2 0 2.2-1.5 4.4-1.5s2.2 1.5 4.4 1.5 2.2-1.5 4.4-1.5M17.4 27.6h9.2" fill="none" stroke="#6BAED6" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  );
}

function PublicIcon({ name }: { name: PublicIconName }) {
  const common = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return (
    <svg className="public-icon" viewBox="0 0 24 24" aria-hidden="true">
      {name === "home" && <><path {...common} d="m4 10 8-6 8 6" /><path {...common} d="M6.5 9v10h11V9M10 19v-5h4v5" /></>}
      {name === "map" && <><path {...common} d="m4 6 5-2 6 2 5-2v14l-5 2-6-2-5 2V6Z" /><path {...common} d="M9 4v14M15 6v14" /></>}
      {name === "shelters" && <><path {...common} d="M4 19h16M6 19V9l6-4 6 4v10" /><path {...common} d="M9.5 19v-5h5v5" /></>}
      {name === "prepare" && <><path {...common} d="m5 12 4 4L19 6" /><path {...common} d="M12 3a9 9 0 1 0 9 9" /></>}
      {name === "data" && <><circle {...common} cx="12" cy="12" r="9" /><path {...common} d="M12 10v6M12 7.2h.01" /></>}
      {name === "change" && <><path {...common} d="M4 7h11M12 4l3 3-3 3M20 17H9M12 14l-3 3 3 3" /></>}
    </svg>
  );
}

export function PublicExperience() {
  const data = useFloodGuardData("mae_sai_candidate_v1");
  const [language, setLanguage] = useLanguage("th");
  const [tab, setTab] = useState<PublicTab>("home");
  const areaPickerRef = useRef<HTMLElement>(null);
  const contentRef = useRef<HTMLElement>(null);
  const th = language === "th";
  const defaultAreaId = data.areas.find((area) => area.area_id === "TH570901")?.area_id
    ?? data.areas[0]?.area_id
    ?? "";
  const householdPlan = useHouseholdPlan(defaultAreaId);
  const persistedArea = data.areas.find((area) => area.area_id === householdPlan.plan.planning_area_id);
  const selected = persistedArea
    ?? data.areas.find((area) => area.area_id === defaultAreaId);
  const selectArea = householdPlan.selectPlanningArea;
  const datasetLabel = th ? "ข้อมูลการวางแผนแม่สาย" : "Mae Sai planning data";
  const hasDecisionEligibleModel = data.model_runs.some((run) => run.can_feed_decision_layer);
  const areaNameTh = selected?.area_name_th ?? "พื้นที่วางแผนไม่พร้อมใช้งาน";
  const areaNameEn = selected?.area_name_en ?? "Planning area unavailable";
  const completedItems = Object.values(householdPlan.plan.checklist).filter(Boolean).length;
  const totalItems = Object.keys(householdPlan.plan.checklist).length;
  const remainingItems = Math.max(0, totalItems - completedItems);
  const readinessProgress = totalItems > 0 ? Math.round((completedItems / totalItems) * 100) : 0;
  const originLabel = data.dataOrigin === "offline_bundle"
    ? (th ? "ข้อมูลแม่สายที่บันทึกไว้ในอุปกรณ์" : "Mae Sai data available on this device")
    : data.dataOrigin === "cached_api"
      ? (th ? "ข้อมูลล่าสุดที่บันทึกไว้" : "Latest saved planning data")
      : data.degradedReason
        ? (th ? "ข้อมูลล่าสุดที่พร้อมใช้งาน" : "Latest available planning data")
        : (th ? "ข้อมูลการวางแผนที่ตรวจสอบแหล่งที่มาและโครงสร้างแล้ว" : "Planning data checked for source and structure");
  const dataStateLabel = PUBLIC_DATA_STATE_LABELS[data.dataState][language];
  const fallbackDetail = data.fallbackReason
    ? (th
      ? "ไม่สามารถตรวจสอบการอัปเดตได้ในขณะนี้ ข้อมูลการวางแผนล่าสุดที่บันทึกไว้ยังพร้อมใช้งาน"
      : "Updates cannot be checked right now. The latest saved planning data remains available.")
    : undefined;
  const degradedDetail = data.degradedReason
    ? (th
      ? "บริการข้อมูลบางส่วนกำลังอัปเดต หน้าจอนี้ใช้ข้อมูลการวางแผนล่าสุดที่พร้อมใช้งาน"
      : "Some data services are updating. This view uses the latest available planning data.")
    : undefined;
  const publicAttributions = visibleLayerAttributions(data.layers, PUBLIC_VISIBLE_LAYER_IDS);

  useEffect(() => {
    if (!persistedArea && defaultAreaId && householdPlan.plan.planning_area_id !== defaultAreaId) {
      selectArea(defaultAreaId);
    }
  }, [defaultAreaId, householdPlan.plan.planning_area_id, persistedArea, selectArea]);

  useEffect(() => {
    contentRef.current?.scrollTo({ top: 0, behavior: "auto" });
  }, [tab]);

  return (
    <main className="public-page" lang={language}>
      <header className="public-header">
        <a href="/public/" className="brand" aria-label="FloodGuard Thailand public preparedness">
          <PublicBrandMark />
          <span><b>FloodGuard</b><small>{th ? "การเตรียมพร้อมของประชาชน" : "Public preparedness"}</small></span>
        </a>
        <LanguageToggle language={language} onChange={setLanguage} />
      </header>

      <section className="public-boundary-banner" aria-label={th ? "ขอบเขตการใช้งานและสถานะข้อมูล" : "Use boundary and data status"}>
        <span className="public-boundary-mark" aria-hidden="true">!</span>
        <div className="public-boundary-copy">
          <strong>{th ? "ข้อมูลเพื่อการเตรียมพร้อม — ตรวจสอบประกาศล่าสุดจาก ปภ. และหน่วยงานท้องถิ่น" : "Preparedness guidance — check current alerts with DDPM and local authorities."}</strong>
          <small>
            <span>{datasetLabel} · {dataStateLabel}</span>
            <span>{originLabel} · {th ? "เวลาข้อมูล" : "Source time"} {formatSourceTime(data.status.source_timestamp, language)} ICT · {th ? "ความเชื่อมั่น" : "Confidence"} {formatConfidence(data.status.confidence_class, language)}</span>
          </small>
          {fallbackDetail && <p className="public-boundary-detail" role="status">{fallbackDetail}</p>}
          {degradedDetail && <p className="public-boundary-detail" role="status">{degradedDetail}</p>}
        </div>
      </section>

      <section ref={contentRef} className="public-content" id="public-active-panel" aria-live="polite">
        {tab === "home" && (
          <>
            <section className="card public-readiness-card" aria-labelledby="public-home-title">
              <div className="public-readiness-heading">
                <div>
                  <p className="eyebrow">{th ? "พื้นที่วางแผนของฉัน" : "My planning area"}</p>
                  <h1 id="public-home-title">{th ? areaNameTh : areaNameEn}</h1>
                </div>
                <button type="button" className="public-change-area" onClick={() => areaPickerRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })}>
                  {th ? "เปลี่ยน" : "Change"}
                </button>
              </div>

              <div className="public-readiness-overview">
                <div
                  className="public-readiness-ring"
                  style={{ "--readiness-progress": `${readinessProgress}%` } as CSSProperties}
                  role="img"
                  aria-label={th ? `ทำเสร็จ ${completedItems} จาก ${totalItems} รายการ` : `${completedItems} of ${totalItems} readiness items complete`}
                >
                  <span><b>{completedItems}/{totalItems}</b><small>{th ? "พร้อม" : "ready"}</small></span>
                </div>
                <div className="public-readiness-copy">
                  <h2>{completedItems === totalItems && totalItems > 0
                    ? (th ? "แผนครัวเรือนพร้อมให้ทบทวน" : "Your household plan is ready to review")
                    : completedItems > 0
                      ? (th ? "แผนครัวเรือนกำลังดำเนินการ" : "Your household plan is in progress")
                      : (th ? "เริ่มแผนเตรียมพร้อมของครัวเรือน" : "Start your household preparedness plan")}</h2>
                  <p>{remainingItems === 0
                    ? (th ? "ทบทวนแผนและยืนยันข้อมูลกับหน่วยงานท้องถิ่น" : "Review it and confirm local information before relying on it.")
                    : (th ? `ทำอีก ${remainingItems} ขั้นตอนเพื่อให้รายการพื้นฐานครบ` : `Finish ${remainingItems} more ${remainingItems === 1 ? "step" : "steps"} to complete the basics.`)}</p>
                </div>
              </div>

              <button
                type="button"
                className="primary-link public-plan-action"
                data-action="build-household-plan"
                aria-controls="public-active-panel"
                onClick={() => setTab("prepare")}
              >
                {completedItems > 0
                  ? (th ? "ทำแผนของฉันต่อ →" : "Continue my plan →")
                  : (th ? "สร้างแผนครัวเรือนของฉัน →" : "Build my household plan →")}
              </button>

              <dl className="public-source-summary" aria-label={th ? "ที่มาโดยย่อ" : "Provenance summary"}>
                <div><dt>{th ? "เวลาข้อมูล" : "Source time"}</dt><dd>{formatSourceTime(data.status.source_timestamp, language)} ICT</dd></div>
                <div><dt>{th ? "ความเชื่อมั่น" : "Confidence"}</dt><dd>{formatConfidence(data.status.confidence_class, language)}</dd></div>
                <div><dt>{th ? "แหล่งข้อมูล" : "Source"}</dt><dd>HDX COD-AB · OpenStreetMap · WorldPop · Copernicus DEM · Sentinel-1</dd></div>
              </dl>
            </section>

            <section className="public-quick-action-section" aria-labelledby="public-quick-actions-title">
              <p className="eyebrow" id="public-quick-actions-title">{th ? "ทางลัด" : "Quick actions"}</p>
              <div className="public-quick-actions">
                <button type="button" onClick={() => setTab("map")}>
                  <span><PublicIcon name="map" /></span><b>{th ? "แผนที่พื้นที่" : "Area map"}</b><small>{th ? "ภาพรวมการวางแผน" : "Planning overview"}</small>
                </button>
                <button type="button" onClick={() => setTab("shelters")}>
                  <span><PublicIcon name="shelters" /></span><b>{th ? "ที่พักพิง" : "Shelters"}</b><small>{th ? "ยืนยันกับท้องถิ่น" : "Confirm locally"}</small>
                </button>
                <button type="button" onClick={() => setTab("data")}>
                  <span><PublicIcon name="data" /></span><b>{th ? "เกี่ยวกับข้อมูล" : "The data"}</b><small>{th ? "ทำอะไรได้บ้าง" : "What it can do"}</small>
                </button>
                <button type="button" className="public-quick-action-primary" onClick={() => areaPickerRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })}>
                  <span><PublicIcon name="change" /></span><b>{th ? "เปลี่ยนพื้นที่" : "Change area"}</b><small>{th ? areaNameTh : areaNameEn}</small>
                </button>
              </div>
            </section>

            <section className="card public-official-help" data-testid="public-official-help" aria-labelledby="official-help-title">
              <div className="public-official-help-heading">
                <h2 id="official-help-title">{th ? "ความช่วยเหลือและประกาศทางการ" : "Official emergency numbers"}</h2>
                <a href="https://www.disaster.go.th/home" target="_blank" rel="noreferrer">
                  {th ? "ประกาศ ปภ. ↗" : "DDPM updates ↗"}
                </a>
              </div>
              <div className="public-hotline-actions">
                {data.hotlines.length > 0 ? data.hotlines.map((hotline) => (
                  <a key={hotline.number} href={hotline.href} aria-label={`${th ? "โทร" : "Call"} ${hotline.number} · ${th ? hotline.label_th : hotline.label_en}`}>
                    <b>{hotline.number}</b><span>{th ? hotline.label_th : hotline.label_en}</span>
                  </a>
                )) : (
                  <p role="status">{th ? "ขณะนี้ไม่มีหมายเลขฉุกเฉินในหน้านี้ โปรดใช้ช่องทางทางการของหน่วยงานท้องถิ่น" : "No emergency numbers are available here right now; use official local-authority channels."}</p>
                )}
              </div>
            </section>

            <section ref={areaPickerRef} className="area-picker card" aria-labelledby="area-picker-title">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">{th ? "พื้นที่วางแผนแบบกว้าง" : "Broad planning area"}</p>
                  <h2 id="area-picker-title">{th ? "เลือกพื้นที่โดยไม่ใช้ตำแหน่งที่อยู่" : "Choose an area without sharing your exact location"}</h2>
                </div>
              </div>
              {data.areas.length > 0 ? (
                <div className="area-chip-row">
                  {data.areas.map((area) => (
                    <button
                      key={area.area_id}
                      type="button"
                      aria-pressed={area.area_id === selected?.area_id}
                      className={area.area_id === selected?.area_id ? "selected" : ""}
                      onClick={() => selectArea(area.area_id)}
                    >
                      <b aria-hidden="true">{area.action_class}</b><span>{th ? area.area_name_th : area.area_name_en}</span>
                    </button>
                  ))}
                </div>
              ) : (
                <p role="status">{th ? "ข้อมูลพื้นที่ไม่พร้อมใช้งานชั่วคราว แต่รายการเตรียมพร้อมทั่วไปยังใช้งานได้" : "Area information is temporarily unavailable. The general household checklist remains available."}</p>
              )}
            </section>

            {selected && (
              <details className="card public-evidence-details">
                <summary>
                  <span>{th ? "ดูหลักฐานการวางแผนโดยละเอียด" : "View detailed planning evidence"}</span>
                  <small>{th ? "คะแนนและชั้นการดำเนินการ" : "Preparedness score and action class"}</small>
                </summary>
                <div className="public-grid">
                  <article className="priority-card">
                    <p className="eyebrow">{th ? "เหตุผลจากแบบจำลอง" : "Modelled reason"}</p>
                    <h2>{th ? "ควรตรวจสอบข้อมูลในพื้นที่" : "Evidence to verify"}</h2>
                    <p>{formatTopReason(selected.action_class, selected.top_reason, language)}</p>
                    <dl className="mini-metrics">
                      <div><dt>FPPS</dt><dd>{selected.fpps_0_100.toFixed(1)}</dd></div>
                      <div><dt>{th ? "ชั้นการดำเนินการ" : "Action class"}</dt><dd>{selected.action_class}</dd></div>
                      <div><dt>{th ? "การเข้าถึง 30 นาที" : "30-min access loss"}</dt><dd>{formatNumber(selected.people_losing_30_min_access, language)} <small>{th ? `คน · ${datasetLabel}` : `people · ${datasetLabel}`}</small></dd></div>
                    </dl>
                  </article>
                  <article className="official-guidance-card">
                    <p className="eyebrow">{th ? "ข้อจำกัด" : "Evidence boundary"}</p>
                    <h2>{th ? "หลักฐานสนับสนุนการวางแผน" : "Planning evidence"}</h2>
                    <p>{th ? "ชั้นและคะแนนนี้ไม่ใช่ระดับเตือนภัยและไม่ใช่คำสั่งให้เดินทาง" : "This class and score are neither a warning level nor an instruction to travel."}</p>
                    <p>{th ? "โอกาสน้ำท่วมใช้บริบท Sentinel-1 และข้อมูลอ้างอิงข้ามพรมแดนใกล้เคียง ส่วนผลกระทบต่อถนนและการเข้าถึงเป็นค่าประมาณเชิงแบบจำลอง โปรดยืนยันสภาพปัจจุบันในพื้นที่" : "Flood likelihood uses Sentinel-1 context and a nearby cross-border reference; road and access impacts are modelled estimates. Confirm current conditions locally."}</p>
                  </article>
                </div>
              </details>
            )}
          </>
        )}

        {tab === "map" && (
          <section className="public-map-view">
            <div className="section-heading"><div><p className="eyebrow">{th ? "ขอบเขตพื้นที่และสถานที่สำคัญ" : "Area boundary & important facilities"}</p><h1>{th ? "แผนที่วางแผนแม่สาย" : "Mae Sai planning map"}</h1></div></div>
            <GeoMap areas={data.areas} selectedId={selected?.area_id ?? ""} onSelect={selectArea} language={language} showRoads={false} showFacilities showAccess={false} height="360px" areaFeatures={data.areaFeatures} roadFeatures={data.roadFeatures} facilityFeatures={data.facilityFeatures} accessFeatures={data.accessFeatures} contextFeatures={data.contextFeatures} datasetMode={data.status.dataset_mode} attributions={publicAttributions} visualPalette="public-blue" enableBasemaps />
            <EvidenceNotice tone="caution" title={th ? "ยืนยันสภาพเส้นทางก่อนเดินทาง" : "Confirm route conditions before travel"}>
              {th ? "ชุดข้อมูลนี้ไม่คำนวณเส้นทางปลอดภัยและไม่แสดงการปิดถนนแบบสด" : "This dataset does not calculate a safe route or show live road closures."}
            </EvidenceNotice>
          </section>
        )}

        {tab === "shelters" && (
          <section className="public-shelter-view">
            <div className="section-heading"><div><p className="eyebrow">{th ? "จุดพักพิง" : "Shelters"}</p><h1>{th ? "ตรวจสอบกับหน่วยงานท้องถิ่นก่อนเดินทาง" : "Confirm locally before travelling"}</h1></div></div>
            {data.shelters.map((shelter) => (
              <article className="card shelter-card" key={shelter.facility_id}>
                <div className="shelter-icon" aria-hidden="true"><PublicIcon name="shelters" /></div>
                <div><p className="eyebrow">{shelter.facility_id}</p><h2>{th ? shelter.name_th : shelter.name_en}</h2><p>{th ? "ความจุและสถานะยังไม่ได้รับการยืนยัน" : "Capacity and current status are not confirmed."}</p><span className="unconfirmed">{th ? "ไม่ยืนยัน" : "Unconfirmed"}</span></div>
              </article>
            ))}
            <article className="card neutral-note">
              <h2>{th ? "เหตุใดจึงไม่มีจำนวนที่ว่าง?" : "Why no availability count?"}</h2>
              <p>{data.shelters.length > 0 ? (th ? "ไม่มีข้อมูลความจุปัจจุบันที่มีเวลาอ้างอิง จึงไม่ประมาณจำนวนที่ว่าง" : "No current, time-stamped capacity information is available, so availability is not estimated.") : (th ? "ขณะนี้ไม่มีข้อมูลที่พักพิงในมุมมองนี้ โปรดยืนยันทางเลือกกับหน่วยงานท้องถิ่น" : "No current shelter information is available in this view. Confirm options with local authorities.")}</p>
              <aside className="public-before-travel"><b>{th ? "ก่อนออกเดินทาง" : "Before you travel"}</b><span>{th ? "โทรยืนยันกับที่พักพิงหรือหน่วยงานท้องถิ่นว่ายังเปิดและเดินทางถึงได้" : "Call the shelter or a local authority to confirm it is open and reachable."}</span></aside>
            </article>
          </section>
        )}

        {tab === "prepare" && (
          <section className="public-prepare-view">
            <div className="section-heading">
              <div>
                <p className="eyebrow">{th ? "แผนครัวเรือนแบบเก็บในอุปกรณ์" : "Device-local household plan"}</p>
                <h1>{th ? "สร้างและทบทวนแผนเตรียมพร้อม" : "Build and review my preparedness plan"}</h1>
              </div>
            </div>
            <HouseholdPlanBuilder
              language={language}
              plan={householdPlan.plan}
              areaNameTh={selected?.area_name_th ?? ""}
              areaNameEn={selected?.area_name_en ?? ""}
              onToggleItem={householdPlan.toggleChecklistItem}
              onToggleNeed={householdPlan.toggleNeed}
              onMarkReviewed={householdPlan.markReviewed}
              onResetChecklist={householdPlan.resetChecklist}
              onClearPlan={householdPlan.clearPlan}
            />
          </section>
        )}

        {tab === "data" && (
          <section className="public-data-view">
            <div className="section-heading"><div><p className="eyebrow">{th ? "เกี่ยวกับข้อมูล" : "About the data"}</p><h1>{th ? "สิ่งที่หน้าจอนี้ทำได้และทำไม่ได้" : "What this screen can and cannot do"}</h1></div></div>
            <div className="about-grid">
              <article className="card public-about-card public-about-capabilities"><h2><span aria-hidden="true">✓</span>{th ? "สิ่งที่มีให้" : "What this provides"}</h2><ul><li>{th ? "แสดงขอบเขตพื้นที่แม่สายและสถานที่สำคัญจากข้อมูลเปิดที่ติดตามแหล่งที่มา" : "Shows Mae Sai area boundaries and important facilities from provenance-tracked open data"}</li><li>{th ? "แสดงคะแนน FPPS และปัจจัยที่อยู่เบื้องหลังลำดับความสำคัญของแต่ละพื้นที่" : "Shows FPPS and the factors behind each area’s planning priority"}</li><li>{th ? "เก็บข้อมูลการวางแผนล่าสุดไว้ใช้งานเมื่อการเชื่อมต่อขัดข้อง" : "Keeps the latest planning data available when connectivity drops"}</li></ul></article>
              <article className="card blocked-card public-about-card"><h2><span aria-hidden="true">×</span>{th ? "สิ่งที่ต้องยืนยันเพิ่มเติม" : "What still needs confirmation"}</h2><ul><li>{th ? "คำเตือนภัยและเส้นทางอพยพปัจจุบันจากหน่วยงานที่รับผิดชอบ" : "Current warnings and evacuation routes from responsible authorities"}</li><li>{th ? "สถานะถนน การเปิดให้บริการ และความจุของที่พักพิงในขณะนี้" : "Current road conditions, facility operation, and shelter capacity"}</li><li>{hasDecisionEligibleModel ? (th ? "ผลแบบจำลองไม่ใช่คำสั่งฉุกเฉิน โปรดติดตามประกาศทางการ" : "Model results are not emergency directions; follow official alerts") : (th ? "ใช้ผลลัพธ์เพื่อจัดลำดับการตรวจสอบและยืนยันกับหน่วยงานท้องถิ่น" : "Use the results to prioritize checks and confirm locally")}</li></ul></article>
            </div>
            <article className="card method-card"><h2>{th ? "วิธีวิเคราะห์การเข้าถึง" : "Access method"}</h2><p>{th ? "เอนจินปัจจุบันเปรียบเทียบเวลาเดินทางสั้นที่สุดไปยังสถานที่ที่ใกล้ที่สุดภายใต้เครือข่ายปกติและเครือข่ายที่ถูกรบกวน ที่เกณฑ์ 15/30/60 นาที ไม่ใช่ 2SFCA ที่คำนึงถึงความจุ" : "The current engine compares shortest travel time to the nearest selected facility under normal and disrupted networks at 15/30/60-minute thresholds. It is not capacity-aware 2SFCA."}</p></article>
            <p className="technical-link"><a href="/studio/">{th ? "เปิดพื้นที่วิจัยและแบบจำลอง →" : "Open the research and model studio →"}</a></p>
          </section>
        )}
      </section>

      <nav className="public-bottom-nav" aria-label={th ? "เมนูหลัก" : "Primary navigation"}>
        {(Object.keys(TAB_LABELS) as PublicTab[]).map((key) => (
          <button key={key} id={`public-tab-${key}`} type="button" aria-controls="public-active-panel" aria-pressed={tab === key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}>
            <span><PublicIcon name={TAB_LABELS[key].icon as PublicIconName} /></span><small>{TAB_LABELS[key][language]}</small>
          </button>
        ))}
      </nav>
    </main>
  );
}
