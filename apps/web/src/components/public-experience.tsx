"use client";

import Image from "next/image";
import { useEffect, useState } from "react";

import { EvidenceNotice } from "@/components/evidence-notice";
import { GeoMap } from "@/components/geo-map";
import { HouseholdPlanBuilder } from "@/components/household-plan-builder";
import { LanguageToggle } from "@/components/language-toggle";
import { StatusBar } from "@/components/status-bar";
import { formatConfidence, formatNumber, formatSourceTime, formatTopReason } from "@/lib/format";
import type { Language } from "@/lib/types";
import { useFloodGuardData } from "@/lib/use-floodguard-data";
import { useHouseholdPlan } from "@/lib/use-household-plan";
import { useLanguage } from "@/lib/use-language";

type PublicTab = "home" | "map" | "shelters" | "prepare" | "data";

const TAB_LABELS: Record<PublicTab, { th: string; en: string; icon: string }> = {
  home: { th: "หน้าแรก", en: "Home", icon: "⌂" },
  map: { th: "แผนที่", en: "Map", icon: "⌖" },
  shelters: { th: "ที่พักพิง", en: "Shelters", icon: "▱" },
  prepare: { th: "เตรียมพร้อม", en: "Prepare", icon: "✓" },
  data: { th: "ข้อมูล", en: "Data", icon: "i" },
};

const PLANNING_SUMMARIES: Record<string, Record<Language, string>> = {
  A: {
    th: "ใช้การฝึกซ้อมนี้เพื่อตรวจรายชื่อผู้ติดต่อ ความต้องการความช่วยเหลือ และข้อมูลท้องถิ่นก่อน",
    en: "Use this rehearsal to check household contacts, support needs, and locally confirmed information first.",
  },
  B: {
    th: "ใช้การฝึกซ้อมนี้เพื่อตรวจทางเลือกการเดินทางหลายทางและยืนยันข้อมูลถนนกับท้องถิ่น",
    en: "Use this rehearsal to check more than one travel option and confirm road information locally.",
  },
  C: {
    th: "ใช้การฝึกซ้อมนี้เพื่อวางแผนสำรองสำหรับยา ไฟฟ้า การติดต่อ และบริการจำเป็น",
    en: "Use this rehearsal to prepare backups for medicine, power, communication, and essential services.",
  },
  D: {
    th: "ใช้การฝึกซ้อมนี้เพื่อปรับปรุงสิ่งของ จุดนัดพบ และแผนช่วยเหลือของครัวเรือน",
    en: "Use this rehearsal to improve supplies, regrouping arrangements, and household support plans.",
  },
  E: {
    th: "หลักฐานสาธิตยังมีความเชื่อมั่นจำกัด จึงควรเตรียมแผนพื้นฐานและตรวจสอบประกาศทางการ",
    en: "The fixture evidence has limited confidence, so prepare a basic plan and verify official notices.",
  },
};

function planningSummary(actionClass: string | undefined, language: Language): string {
  return PLANNING_SUMMARIES[actionClass ?? ""]?.[language]
    ?? (language === "th"
      ? "เตรียมแผนครัวเรือนและยืนยันข้อมูลกับหน่วยงานท้องถิ่นก่อนตัดสินใจ"
      : "Prepare a household plan and confirm information with local authorities before acting.");
}

export function PublicExperience() {
  const data = useFloodGuardData();
  const [language, setLanguage] = useLanguage("th");
  const [tab, setTab] = useState<PublicTab>("home");
  const th = language === "th";
  const defaultAreaId = data.areas.find((area) => area.area_id === "FG-TB-002")?.area_id
    ?? data.areas[0]?.area_id
    ?? "";
  const householdPlan = useHouseholdPlan(defaultAreaId);
  const persistedArea = data.areas.find((area) => area.area_id === householdPlan.plan.planning_area_id);
  const selected = persistedArea
    ?? data.areas.find((area) => area.area_id === defaultAreaId);
  const selectArea = householdPlan.selectPlanningArea;
  const datasetLabel = data.status.dataset_mode === "fixture_demo"
    ? (th ? "ชุดข้อมูลสาธิต" : "Fixture demo")
    : data.status.dataset_mode === "candidate"
      ? (th ? "ข้อมูลผู้สมัคร" : "Candidate data")
      : (th ? "ข้อมูลนำเข้าทางการ" : "Official input");
  const hasDecisionEligibleModel = data.model_runs.some((run) => run.can_feed_decision_layer);
  const areaNameTh = selected?.area_name_th ?? "พื้นที่วางแผนไม่พร้อมใช้งาน";
  const areaNameEn = selected?.area_name_en ?? "Planning area unavailable";

  useEffect(() => {
    if (!persistedArea && defaultAreaId && householdPlan.plan.planning_area_id !== defaultAreaId) {
      selectArea(defaultAreaId);
    }
  }, [defaultAreaId, householdPlan.plan.planning_area_id, persistedArea, selectArea]);

  return (
    <main className="public-page" lang={language}>
      <header className="public-header">
        <a href="/public/" className="brand" aria-label="FloodGuard Thailand public preparedness">
          <Image src="/icon.svg" alt="" width={42} height={42} priority />
          <span><b>FloodGuard</b><small>{th ? "การเตรียมพร้อมของประชาชน" : "Public preparedness"}</small></span>
        </a>
        <LanguageToggle language={language} onChange={setLanguage} />
      </header>

      <StatusBar data={data} language={language} compact />

      <section className="public-content" id="public-active-panel" aria-live="polite">
        {tab === "home" && (
          <>
            <section className="hero-status public-action-hero card" aria-labelledby="public-home-title">
              <div className="public-action-hero-content">
                <p className="public-permanent-warning" role="note">
                  <span aria-hidden="true">!</span>
                  {th ? "FloodGuard ไม่ใช่ประกาศทางการ" : "FloodGuard is not an official warning"}
                </p>
                <p className="eyebrow">{th ? `พื้นที่วางแผนของฉัน · ${datasetLabel}` : `My planning area · ${datasetLabel}`}</p>
                <h1 id="public-home-title">{th ? areaNameTh : areaNameEn}</h1>
                <p className="public-plain-summary">{planningSummary(selected?.action_class, language)}</p>
                <div className="public-primary-actions">
                  <button
                    type="button"
                    className="primary-link"
                    data-action="build-household-plan"
                    aria-controls="public-active-panel"
                    onClick={() => setTab("prepare")}
                  >
                    {th ? "สร้างแผนครัวเรือนของฉัน" : "Build my household plan"}
                  </button>
                  <a href="https://www.disaster.go.th/home" target="_blank" rel="noreferrer">
                    {th ? "ดูประกาศ ปภ. อย่างเป็นทางการ ↗" : "Check official DDPM updates ↗"}
                  </a>
                </div>
                <dl className="public-source-summary" aria-label={th ? "ที่มาโดยย่อ" : "Provenance summary"}>
                  <div><dt>{th ? "เวลาข้อมูล" : "Source time"}</dt><dd>{formatSourceTime(data.status.source_timestamp, language)} ICT</dd></div>
                  <div><dt>{th ? "ความเชื่อมั่น" : "Confidence"}</dt><dd>{formatConfidence(data.status.confidence_class, language)}</dd></div>
                  <div><dt>{th ? "แหล่งข้อมูล" : "Source"}</dt><dd>{data.status.source_name}</dd></div>
                </dl>
              </div>
            </section>

            <section className="card public-official-help" data-testid="public-official-help" aria-labelledby="official-help-title">
              <div>
                <p className="eyebrow">{th ? "ความช่วยเหลือและประกาศทางการ" : "Official help and updates"}</p>
                <h2 id="official-help-title">{th ? "ใช้ช่องทางทางการเมื่อจำเป็น" : "Use official channels when needed"}</h2>
                <p>{th ? "FloodGuard ไม่ออกคำสั่งอพยพ โปรดติดตาม ปภ. กรมอุตุนิยมวิทยา และหน่วยงานท้องถิ่น" : "FloodGuard does not issue evacuation orders. Follow DDPM, TMD, and local authorities."}</p>
              </div>
              <div className="public-hotline-actions">
                {data.hotlines.length > 0 ? data.hotlines.map((hotline) => (
                  <a key={hotline.number} href={hotline.href} aria-label={`${th ? "โทร" : "Call"} ${hotline.number} · ${th ? hotline.label_th : hotline.label_en}`}>
                    <b>{hotline.number}</b><span>{th ? hotline.label_th : hotline.label_en}</span><small>{th ? "โทร" : "Call"}</small>
                  </a>
                )) : (
                  <p role="status">{th ? "ไม่มีหมายเลขที่ผ่านสัญญาข้อมูล โปรดใช้ช่องทางหน่วยงานท้องถิ่น" : "No contracted hotline records are available; use official local-authority channels."}</p>
                )}
              </div>
            </section>

            <section className="area-picker card" aria-labelledby="area-picker-title">
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
                <p role="status">{th ? "ยังไม่มีพื้นที่ที่ผ่านสัญญาข้อมูล แผนครัวเรือนยังใช้รายการทั่วไปได้" : "No area records currently pass the data contract. The general household checklist remains available."}</p>
              )}
            </section>

            {selected && (
              <details className="card public-evidence-details">
                <summary>
                  <span>{th ? "ดูหลักฐานการวางแผนโดยละเอียด" : "View detailed planning evidence"}</span>
                  <small>{th ? "คะแนนและชั้นสาธิต" : "Fixture score and class"}</small>
                </summary>
                <div className="public-grid">
                  <article className="priority-card">
                    <p className="eyebrow">{th ? "เหตุผลจากแบบจำลอง" : "Modelled reason"}</p>
                    <h2>{th ? "ควรตรวจสอบข้อมูลในพื้นที่" : "Evidence to verify"}</h2>
                    <p>{formatTopReason(selected.action_class, selected.top_reason, language)}</p>
                    <dl className="mini-metrics">
                      <div><dt>FPPS</dt><dd>{selected.fpps_0_100.toFixed(1)}</dd></div>
                      <div><dt>{th ? "ชั้นสาธิต" : "Fixture class"}</dt><dd>{selected.action_class}</dd></div>
                      <div><dt>{th ? "การเข้าถึง 30 นาที" : "30-min access loss"}</dt><dd>{formatNumber(selected.people_losing_30_min_access, language)} <small>{th ? `คน · ${datasetLabel}` : `people · ${datasetLabel}`}</small></dd></div>
                    </dl>
                  </article>
                  <article className="official-guidance-card">
                    <p className="eyebrow">{th ? "ข้อจำกัด" : "Evidence boundary"}</p>
                    <h2>{th ? "ข้อมูลเพื่อการฝึกวางแผน" : "Planning rehearsal evidence"}</h2>
                    <p>{th ? "ชั้นและคะแนนนี้ไม่ใช่ระดับเตือนภัยและไม่ใช่คำสั่งให้เดินทาง" : "This class and score are neither a warning level nor an instruction to travel."}</p>
                  </article>
                </div>
              </details>
            )}
          </>
        )}

        {tab === "map" && (
          <section className="public-map-view">
            <div className="section-heading"><div><p className="eyebrow">{th ? `แผนที่ GeoJSON · ${datasetLabel}` : `GeoJSON map · ${datasetLabel}`}</p><h1>{th ? "ภาพรวมพื้นที่เพื่อการฝึกซ้อม" : "Area planning rehearsal"}</h1></div></div>
            <GeoMap areas={data.areas} selectedId={selected?.area_id ?? ""} onSelect={selectArea} language={language} showRoads={false} height="390px" areaFeatures={data.areaFeatures} roadFeatures={data.roadFeatures} contextFeatures={data.contextFeatures} datasetMode={data.status.dataset_mode} />
            <EvidenceNotice tone="caution" title={th ? "เส้นทางใช้เพื่อการซ้อมเตรียมพร้อมเท่านั้น" : "Routes are for preparedness rehearsal only"}>
              {th ? "ชุดข้อมูลนี้ไม่คำนวณเส้นทางปลอดภัยและไม่แสดงการปิดถนนแบบสด" : "This dataset does not calculate a safe route or show live road closures."}
            </EvidenceNotice>
          </section>
        )}

        {tab === "shelters" && (
          <section>
            <div className="section-heading"><div><p className="eyebrow">{th ? "จุดพักพิง" : "Shelters"}</p><h1>{th ? "ตรวจสอบกับหน่วยงานท้องถิ่นก่อนเดินทาง" : "Confirm locally before travelling"}</h1></div></div>
            {data.shelters.map((shelter) => (
              <article className="card shelter-card" key={shelter.facility_id}>
                <div className="shelter-icon" aria-hidden="true">⌂</div>
                <div><p className="eyebrow">{shelter.facility_id}</p><h2>{th ? shelter.name_th : shelter.name_en}</h2><p>{th ? "ความจุและสถานะยังไม่ได้รับการยืนยัน" : "Capacity and current status are not confirmed."}</p></div>
                <span className="unconfirmed">{th ? "ไม่ยืนยัน" : "Unconfirmed"}</span>
              </article>
            ))}
            <article className="card neutral-note"><h2>{th ? "เหตุใดจึงไม่มีจำนวนที่ว่าง?" : "Why no availability count?"}</h2><p>{data.shelters.length > 0 ? (th ? "ข้อมูลสถานที่ไม่มีสัญญาความจุพร้อมเวลา จึงไม่สร้างจำนวนที่ว่างขึ้นเอง" : "The facility data has no time-stamped capacity contract, so the app does not invent availability.") : (th ? "ชุดข้อมูลปัจจุบันไม่มีรายการสถานที่พักพิงที่ผ่านสัญญาข้อมูล" : "The current dataset provides no shelter records that pass the data contract.")}</p></article>
          </section>
        )}

        {tab === "prepare" && (
          <section>
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
          <section>
            <div className="section-heading"><div><p className="eyebrow">{th ? "เกี่ยวกับข้อมูล" : "About the data"}</p><h1>{th ? "สิ่งที่หน้าจอนี้ทำได้และทำไม่ได้" : "What this screen can and cannot do"}</h1></div></div>
            <div className="about-grid">
              <article className="card"><h2>{th ? "ทำได้" : "What it demonstrates"}</h2><ul><li>{th ? "อ่าน GeoJSON ที่ผ่านสัญญาข้อมูลตามสถานะที่แสดง" : "Reads schema-governed GeoJSON with its visible data state"}</li><li>{th ? "แสดงคะแนน FPPS และเหตุผลจากเอนจินที่ทดสอบแล้ว" : "Shows FPPS and reasons from the tested engine"}</li><li>{th ? "เก็บสำเนาสาธิตที่มีป้ายกำกับไว้ใช้ออฟไลน์" : "Keeps a labelled fixture snapshot for offline judging"}</li></ul></article>
              <article className="card blocked-card"><h2>{th ? "ยังทำไม่ได้" : "What remains unavailable"}</h2><ul><li>{th ? "การเตือนภัยหรือการนำทางอพยพแบบสด" : "Live warning or evacuation navigation"}</li><li>{th ? "สถานะถนนและที่พักพิงที่ยืนยันแล้ว" : "Verified live road or shelter status"}</li><li>{hasDecisionEligibleModel ? (th ? "สถานะผ่านเกณฑ์ของแบบจำลองไม่เปลี่ยนหน้าจอนี้เป็นคำสั่งฉุกเฉิน" : "Model eligibility does not turn this screen into emergency direction") : (th ? "ยังไม่มีแบบจำลองที่ผ่านเกณฑ์เพื่อส่งต่อชั้นการตัดสินใจ" : "No model run is cleared to feed the decision layer")}</li></ul></article>
            </div>
            <article className="card method-card"><h2>{th ? "วิธีวิเคราะห์การเข้าถึง" : "Access method"}</h2><p>{th ? "เอนจินปัจจุบันเปรียบเทียบเวลาเดินทางสั้นที่สุดไปยังสถานที่ที่ใกล้ที่สุดภายใต้เครือข่ายปกติและเครือข่ายที่ถูกรบกวน ที่เกณฑ์ 15/30/60 นาที ไม่ใช่ 2SFCA ที่คำนึงถึงความจุ" : "The current engine compares shortest travel time to the nearest selected facility under normal and disrupted networks at 15/30/60-minute thresholds. It is not capacity-aware 2SFCA."}</p></article>
            <p className="technical-link"><a href="/studio/">{th ? "เปิดพื้นที่วิจัยและแบบจำลอง →" : "Open the research and model studio →"}</a></p>
          </section>
        )}
      </section>

      <nav className="public-bottom-nav" aria-label={th ? "เมนูหลัก" : "Primary navigation"}>
        {(Object.keys(TAB_LABELS) as PublicTab[]).map((key) => (
          <button key={key} id={`public-tab-${key}`} type="button" aria-controls="public-active-panel" aria-pressed={tab === key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}>
            <span aria-hidden="true">{TAB_LABELS[key].icon}</span><small>{TAB_LABELS[key][language]}</small>
          </button>
        ))}
      </nav>
    </main>
  );
}
