"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { EvidenceNotice } from "@/components/evidence-notice";
import { GeoMap } from "@/components/geo-map";
import { HouseholdPlanBuilder } from "@/components/household-plan-builder";
import { LanguageToggle } from "@/components/language-toggle";
import { formatConfidence, formatNumber, formatSourceTime } from "@/lib/format";
import { countCompletedPlanItems } from "@/lib/household-plan";
import { visibleLayerAttributions } from "@/lib/map-attribution";
import type { FeatureCollection } from "@/lib/types";
import { usePublicFloodGuardData } from "@/lib/use-public-floodguard-data";
import { useHouseholdPlan } from "@/lib/use-household-plan";
import { useLanguage } from "@/lib/use-language";

type PublicTab = "home" | "map" | "shelters" | "prepare" | "data";

const TAB_LABELS: Record<PublicTab, { th: string; en: string; icon: string }> = {
  home: { th: "หน้าแรก", en: "Home", icon: "home" },
  map: { th: "แผนที่", en: "Map", icon: "map" },
  shelters: { th: "คำแนะนำที่พักพิง", en: "Shelter guidance", icon: "shelters" },
  prepare: { th: "เตรียมพร้อม", en: "Prepare", icon: "prepare" },
  data: { th: "ข้อมูล", en: "Data", icon: "data" },
};

const PUBLIC_DATA_STATE_LABELS = {
  loading: { th: "กำลังตรวจสอบชุดข้อมูล", en: "Checking the data package" },
  ready: { th: "ข้อมูลประวัติศาสตร์พร้อมใช้งาน", en: "Historical information available" },
  stale: { th: "ข้อมูลปัจจุบันต้องได้รับการยืนยัน", en: "Current conditions need confirmation" },
  stale_offline: { th: "ใช้สำเนาประวัติศาสตร์ในอุปกรณ์", en: "Using the historical copy on this device" },
  blocked: { th: "ไม่สามารถยืนยันสภาพปัจจุบันได้", en: "Current conditions cannot be confirmed" },
  unavailable: { th: "ข้อมูลการวางแผนไม่พร้อมใช้", en: "Planning information unavailable" },
} as const;

const CONFIRMED_PUBLIC_FACILITY_STATES = new Set([
  "authoritative",
  "confirmed",
  "locally_confirmed",
  "official_confirmed",
  "verified",
]);
const CONFIRMED_PUBLIC_EMERGENCY_ROLES = new Set([
  "agency_verified",
  "confirmed_shelter",
  "designated_shelter",
  "official_shelter",
]);

const EMPTY_PUBLIC_ROADS: FeatureCollection = { type: "FeatureCollection", name: "public_roads_withheld", features: [] };
const EMPTY_PUBLIC_FACILITIES: FeatureCollection = { type: "FeatureCollection", name: "public_facilities_withheld", features: [] };
const EMPTY_PUBLIC_ACCESS: FeatureCollection = { type: "FeatureCollection", name: "public_access_withheld", features: [] };
const EMPTY_PUBLIC_CONTEXT: FeatureCollection = { type: "FeatureCollection", name: "public_context_withheld", features: [] };

type PublicIconName = PublicTab | "change";

export function projectPublicFacilityFeatures(features: FeatureCollection): FeatureCollection {
  return {
    ...features,
    name: `${features.name}_public_confirmed`,
    features: features.features.filter((feature) => {
      const verification = String(feature.properties.verification_status ?? "").toLowerCase();
      const candidateStatus = String(feature.properties.candidate_status ?? "").toLowerCase();
      const emergencyRole = String(feature.properties.emergency_role ?? "").toLowerCase();
      const isShelter = String(feature.properties.facility_type ?? "").toLowerCase().includes("shelter");
      const hasConfirmedEmergencyRole = CONFIRMED_PUBLIC_EMERGENCY_ROLES.has(emergencyRole);
      return CONFIRMED_PUBLIC_FACILITY_STATES.has(verification)
        && !candidateStatus.includes("candidate")
        && (!isShelter || hasConfirmedEmergencyRole);
    }),
  };
}

function publicRecommendationLabel(code: string, language: "th" | "en"): string {
  const labels: Record<string, { th: string; en: string }> = {
    low_confidence: {
      th: "ตรวจสอบข้อมูลกับหน่วยงานท้องถิ่นก่อนนำไปใช้วางแผน",
      en: "Verify the evidence with local authorities before using it for planning.",
    },
    low_priority_score: {
      th: "ติดตามข้อมูลและทบทวนแผนเตรียมพร้อมตามประกาศทางการ",
      en: "Monitor official information and keep the preparedness plan under review.",
    },
    life_safety_exposure: {
      th: "ให้ความสำคัญกับการตรวจสอบความต้องการด้านความปลอดภัยของชีวิต",
      en: "Prioritize local checks for life-safety needs.",
    },
    critical_route_access: {
      th: "ตรวจสอบเส้นทางสำคัญและทางเลือกกับหน่วยงานท้องถิ่น",
      en: "Confirm critical routes and alternatives with local authorities.",
    },
    essential_service_access: {
      th: "ตรวจสอบการเข้าถึงบริการจำเป็นและแผนสำรองในพื้นที่",
      en: "Confirm access to essential services and local backup plans.",
    },
    resilience: {
      th: "ทบทวนมาตรการเตรียมพร้อมและความยืดหยุ่นระยะยาว",
      en: "Review longer-term preparedness and resilience measures.",
    },
  };
  return labels[code]?.[language]
    ?? (language === "th" ? "ตรวจสอบข้อมูลกับหน่วยงานท้องถิ่น" : "Verify the evidence with local authorities.");
}

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
  const data = usePublicFloodGuardData();
  const [language, setLanguage] = useLanguage("th");
  const [tab, setTab] = useState<PublicTab>("home");
  const areaSelectRef = useRef<HTMLSelectElement>(null);
  const contentRef = useRef<HTMLElement>(null);
  const th = language === "th";
  const householdPlan = useHouseholdPlan("");
  const selected = data.publicAreas.find((area) => area.area_id === householdPlan.plan.planning_area_id);
  const selectedAreaId = selected?.area_id ?? "";
  const selectArea = householdPlan.selectPlanningArea;
  const publicFacilityFeatures = useMemo(
    () => projectPublicFacilityFeatures(EMPTY_PUBLIC_FACILITIES),
    [],
  );
  const publicLayerIds = useMemo(
    () => new Set(["public_preparedness_areas"]),
    [],
  );
  const publicAttributions = visibleLayerAttributions(data.layers, publicLayerIds, "public");
  const hasDecisionEligibleModel = data.evidenceRecord?.operational_authorized === true;
  const completedItems = countCompletedPlanItems(householdPlan.plan);
  const selectedNeeds = Object.values(householdPlan.plan.needs).filter(Boolean).length;
  const needsSummary = householdPlan.plan.needs_review_state === "selected"
    ? (th ? `เลือกแล้ว ${selectedNeeds} ข้อ` : `${selectedNeeds} selected`)
    : householdPlan.plan.needs_review_state === "none_apply"
      ? (th ? "ยืนยันว่าไม่มีข้อใดใช้" : "None apply")
      : (th ? "ยังไม่ได้ทบทวน" : "Not reviewed");
  const dataStateLabel = PUBLIC_DATA_STATE_LABELS[data.dataState][language];
  const fallbackDetail = data.fallbackReason
    ? (th
      ? "ไม่สามารถตรวจสอบชุดข้อมูลจากเครือข่ายได้ ขณะนี้กำลังใช้สำเนาประวัติศาสตร์ที่บันทึกไว้ในอุปกรณ์"
      : "The network data package cannot be checked. The historical copy saved on this device is being used.")
    : undefined;
  const degradedDetail = data.degradedReason
    ? (th
      ? "บริการข้อมูลบางส่วนไม่พร้อมใช้งาน ข้อมูลนี้ยังคงเป็นหลักฐานประวัติศาสตร์และไม่ยืนยันสภาพปัจจุบัน"
      : "Some data services are unavailable. This remains historical evidence and does not confirm current conditions.")
    : undefined;

  useEffect(() => {
    if (data.publicAreas.length > 0 && householdPlan.plan.planning_area_id && !selected) {
      selectArea("");
    }
  }, [data.publicAreas.length, householdPlan.plan.planning_area_id, selectArea, selected]);

  useEffect(() => {
    contentRef.current?.scrollTo({ top: 0, behavior: "auto" });
  }, [tab]);

  const openPlan = () => {
    if (!selected && data.publicAreas.length > 0) {
      areaSelectRef.current?.focus();
      return;
    }
    setTab("prepare");
  };

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
          <strong>{th ? "ข้อมูลประวัติศาสตร์เพื่อการเตรียมพร้อม — ตรวจสอบประกาศปัจจุบันจาก ปภ. และหน่วยงานท้องถิ่น" : "Historical preparedness information — check current alerts with DDPM and local authorities."}</strong>
          <small>
            <span>{th ? "บริบทอุทกภัยแม่สาย เดือนกันยายน 2567" : "Mae Sai flood context · September 2024"} · {dataStateLabel}</span>
            <span>{th ? "วันที่หลักฐาน" : "Evidence date"} {formatSourceTime(data.status.source_timestamp, language)} ICT · {th ? "ความเชื่อมั่นของแบบจำลอง" : "Model confidence"} {formatConfidence(data.status.confidence_class, language)}</span>
          </small>
          {fallbackDetail && <p className="public-boundary-detail" role="status">{fallbackDetail}</p>}
          {degradedDetail && <p className="public-boundary-detail" role="status">{degradedDetail}</p>}
        </div>
      </section>

      <section ref={contentRef} className="public-content" id="public-active-panel" aria-live="polite">
        {tab === "home" && (
          <>
            <section className="card public-official-update" aria-labelledby="public-official-update-title">
              <div>
                <p className="eyebrow">{th ? "ข้อมูลปัจจุบันจากหน่วยงานทางการ" : "Current official information"}</p>
                <h1 id="public-official-update-title">{th ? "ตรวจสอบประกาศก่อนตัดสินใจ" : "Check official updates before deciding"}</h1>
                <p>{th ? "FloodGuard ไม่ออกคำเตือนหรือคำสั่งอพยพ" : "FloodGuard does not issue warnings or evacuation orders."}</p>
              </div>
              <a className="primary-link" href="https://www.disaster.go.th/home" target="_blank" rel="noreferrer">
                {th ? "เปิดประกาศของ ปภ. ↗" : "Open DDPM updates ↗"}
              </a>
            </section>

            <section className="card public-plan-overview" aria-labelledby="public-home-title">
              <div className="public-plan-overview-heading">
                <div>
                  <p className="eyebrow">{th ? "แผนที่เก็บในอุปกรณ์นี้" : "Plan stored on this device"}</p>
                  <h2 id="public-home-title">{th ? "แผนเตรียมพร้อมของครัวเรือน" : "Household preparedness plan"}</h2>
                </div>
                <PublicIcon name="prepare" />
              </div>
              <dl className="public-plan-segments">
                <div><dt>{th ? "รายการพื้นฐาน" : "Core actions"}</dt><dd>{completedItems}/{Object.keys(householdPlan.plan.checklist).length}</dd></div>
                <div><dt>{th ? "ความต้องการ" : "Needs"}</dt><dd>{needsSummary}</dd></div>
                <div><dt>{th ? "การทบทวน" : "Review"}</dt><dd>{householdPlan.plan.last_reviewed_at ? (th ? "บันทึกแล้ว" : "Recorded") : (th ? "ยังไม่บันทึก" : "Not recorded")}</dd></div>
              </dl>
              <p className="public-plan-boundary">{th ? "สถานะนี้บอกเฉพาะสิ่งที่บันทึกไว้ ไม่ใช่คะแนนความปลอดภัย" : "This reports only what is recorded; it is not a household safety score."}</p>
              <button type="button" className="primary-link public-plan-action" data-action="build-household-plan" onClick={openPlan}>
                {!selected && data.publicAreas.length > 0
                  ? (th ? "เลือกพื้นที่เพื่อดำเนินการต่อ" : "Choose an area to continue")
                  : completedItems > 0 || householdPlan.plan.needs_review_state !== "not_reviewed"
                    ? (th ? "ทำแผนของฉันต่อ →" : "Continue my plan →")
                    : (th ? "เริ่มแผนครัวเรือน →" : "Start my household plan →")}
              </button>
            </section>

            <section className="card public-area-selection" aria-labelledby="area-picker-title">
              <div>
                <p className="eyebrow">{th ? "พื้นที่วางแผนแบบกว้าง" : "Broad planning area"}</p>
                <h2 id="area-picker-title">{th ? "เลือกพื้นที่โดยไม่เปิดเผยตำแหน่งที่แน่นอน" : "Choose an area without sharing your exact location"}</h2>
              </div>
              <label htmlFor="public-area-select">{th ? "พื้นที่ของฉัน" : "My planning area"}</label>
              <select
                ref={areaSelectRef}
                id="public-area-select"
                value={selectedAreaId}
                onChange={(event) => selectArea(event.target.value)}
                disabled={data.publicAreas.length === 0}
              >
                <option value="">{data.publicAreas.length === 0
                  ? (th ? "กำลังโหลดพื้นที่…" : "Loading areas…")
                  : (th ? "เลือกพื้นที่" : "Choose an area")}</option>
                {data.publicAreas.map((area) => <option key={area.area_id} value={area.area_id}>{th ? area.area_name_th : area.area_name_en}</option>)}
              </select>
              <small>{th ? "การเลือกนี้เก็บในอุปกรณ์ ระบบไม่ขอพิกัดหรือที่อยู่บ้าน" : "This selection stays on your device. No coordinates or home address are requested."}</small>
            </section>

            {selected ? (
              <section className="card public-planning-focus" aria-labelledby="public-planning-focus-title">
                <p className="eyebrow">{th ? "จุดเน้นจากแบบจำลองประวัติศาสตร์" : "Historical modelled planning focus"}</p>
                <h2 id="public-planning-focus-title">{th ? selected.area_name_th : selected.area_name_en}</h2>
                <p>{publicRecommendationLabel(selected.recommendation_code, language)}</p>
                <dl>
                  <div><dt>{th ? "ลำดับความสำคัญในการวางแผน" : "Planning priority"}</dt><dd>{formatNumber(selected.planning_priority_0_100, language, 1)} / 100</dd></div>
                  <div><dt>{th ? "ความเพียงพอของหลักฐาน" : "Evidence sufficiency"}</dt><dd>{formatConfidence(selected.evidence_sufficiency, language)}</dd></div>
                  <div><dt>{th ? "สภาพปัจจุบัน" : "Current conditions"}</dt><dd>{selected.current_conditions_confirmed ? (th ? "ยืนยันแล้ว" : "Confirmed") : (th ? "ยังไม่ได้รับการยืนยัน" : "Not confirmed")}</dd></div>
                </dl>
                <div className="public-confirm-list">
                  <b>{th ? "สิ่งที่ต้องยืนยันก่อนดำเนินการ" : "What to confirm before acting"}</b>
                  <ul>
                    <li>{th ? "ประกาศและคำแนะนำปัจจุบันจาก ปภ. หรือหน่วยงานท้องถิ่น" : "Current alerts and instructions from DDPM or local authorities"}</li>
                    <li>{th ? "สภาพถนน สะพาน และทางเข้าถึงในขณะนี้" : "Current road, bridge, and access conditions"}</li>
                    <li>{th ? "การเปิดให้บริการ บทบาท ความจุ และการเข้าถึงของสถานที่" : "Facility operation, role, capacity, and accessibility"}</li>
                  </ul>
                </div>
              </section>
            ) : (
              <section className="card public-no-area" aria-labelledby="public-no-area-title">
                <h2 id="public-no-area-title">{th ? "ยังไม่ได้เลือกพื้นที่" : "No planning area selected"}</h2>
                <p>{th ? "เลือกพื้นที่แบบกว้างด้านบนเพื่อดูจุดเน้นการวางแผน โดยไม่ต้องเปิดเผยตำแหน่งบ้าน" : "Choose a broad area above to see its planning focus without sharing your home location."}</p>
              </section>
            )}

            <section className="card public-official-help" data-testid="public-official-help" aria-labelledby="official-help-title">
              <div className="public-official-help-heading">
                <h2 id="official-help-title">{th ? "หมายเลขฉุกเฉินทางการ" : "Official emergency numbers"}</h2>
                <a href="https://www.disaster.go.th/home" target="_blank" rel="noreferrer">{th ? "ประกาศ ปภ. ↗" : "DDPM updates ↗"}</a>
              </div>
              <div className="public-hotline-actions">
                {data.hotlines.length > 0 ? data.hotlines.map((hotline) => (
                  <a key={hotline.number} href={hotline.href} aria-label={`${th ? "โทร" : "Call"} ${hotline.number} · ${th ? hotline.label_th : hotline.label_en}`}>
                    <b>{hotline.number}</b><span>{th ? hotline.label_th : hotline.label_en}</span>
                  </a>
                )) : (
                  <>
                    <a href="tel:1784" aria-label={th ? "โทร 1784 สายด่วนนิรภัย ปภ." : "Call 1784 DDPM disaster hotline"}><b>1784</b><span>{th ? "สายด่วนนิรภัย ปภ." : "DDPM disaster hotline"}</span></a>
                    <a href="tel:1669" aria-label={th ? "โทร 1669 การแพทย์ฉุกเฉิน" : "Call 1669 emergency medical service"}><b>1669</b><span>{th ? "การแพทย์ฉุกเฉิน" : "Emergency medical service"}</span></a>
                  </>
                )}
              </div>
            </section>
          </>
        )}

        {tab === "map" && (
          <section className="public-map-view">
            <div className="section-heading"><div><p className="eyebrow">{th ? "ขอบเขตพื้นที่ประวัติศาสตร์" : "Historical area context"}</p><h1>{th ? "แผนที่วางแผนแม่สาย" : "Mae Sai planning map"}</h1></div></div>
            <GeoMap
              areas={data.publicAreas}
              selectedId={selectedAreaId}
              onSelect={selectArea}
              language={language}
              showRoads={false}
              showFacilities={publicFacilityFeatures.features.length > 0}
              showAccess={false}
              height="360px"
              areaFeatures={data.areaFeatures}
              roadFeatures={EMPTY_PUBLIC_ROADS}
              facilityFeatures={publicFacilityFeatures}
              accessFeatures={EMPTY_PUBLIC_ACCESS}
              contextFeatures={EMPTY_PUBLIC_CONTEXT}
              datasetMode={data.status.dataset_mode}
              attributions={publicAttributions}
              visualPalette="public-blue"
              enableBasemaps
            />
            <EvidenceNotice tone="caution" title={th ? "ตรวจสอบสภาพปัจจุบันก่อนเดินทาง" : "Check current conditions before travel"}>
              {th ? "แผนที่นี้ใช้หลักฐานประวัติศาสตร์ ไม่คำนวณเส้นทางปลอดภัย และไม่แสดงการปิดถนนหรือสถานะสถานที่แบบปัจจุบัน" : "This map uses historical evidence. It does not calculate a safe route or show current road closures or facility status."}
            </EvidenceNotice>
          </section>
        )}

        {tab === "shelters" && (
          <section className="public-shelter-view">
            <div className="section-heading"><div><p className="eyebrow">{th ? "คำแนะนำที่พักพิง" : "Shelter guidance"}</p><h1>{th ? "ยืนยันจุดหมายก่อนออกเดินทาง" : "Confirm a destination before travelling"}</h1></div></div>
            <article className="card shelter-guidance-status">
              <div className="shelter-icon" aria-hidden="true"><PublicIcon name="shelters" /></div>
              <div>
                <h2>{th ? "ยังไม่มีจุดพักพิงที่ยืนยันแล้วในมุมมองนี้" : "No confirmed shelters are published in this view"}</h2>
                <p>{th ? "ข้อมูลเปิดเกี่ยวกับสถานที่ไม่ได้ยืนยันการกำหนดเป็นที่พักพิง การเปิดให้บริการ ความจุ หรือการเดินทางถึงในขณะนี้" : "Open facility data does not confirm shelter designation, current operation, capacity, or reachability."}</p>
              </div>
            </article>
            <article className="card shelter-official-action">
              <p className="eyebrow">{th ? "ยืนยันกับหน่วยงานทางการ" : "Confirm with an official source"}</p>
              <h2>{th ? "โทร 1784 หรือดูประกาศของ ปภ." : "Call DDPM 1784 or check official updates"}</h2>
              <div>
                <a className="primary-link" href="tel:1784">{th ? "โทร 1784" : "Call 1784"}</a>
                <a href="https://www.disaster.go.th/home" target="_blank" rel="noreferrer">{th ? "เปิดประกาศของ ปภ. ↗" : "Open DDPM updates ↗"}</a>
              </div>
            </article>
            <article className="card shelter-before-leaving" aria-labelledby="before-leaving-title">
              <h2 id="before-leaving-title">{th ? "ตรวจสอบก่อนออกเดินทาง" : "Before leaving, confirm"}</h2>
              <ol>
                <li>{th ? "สถานที่ได้รับการกำหนดให้ใช้เป็นที่พักพิงและเปิดอยู่" : "The destination is designated for shelter use and is open"}</li>
                <li>{th ? "มีพื้นที่หรือความจุสำหรับสมาชิกในครัวเรือน" : "Space or capacity is available for your household"}</li>
                <li>{th ? "เส้นทางยังเดินทางถึงได้ตามคำแนะนำปัจจุบัน" : "The route is reachable under current official guidance"}</li>
                <li>{th ? "รองรับการเคลื่อนไหว สุขภาพ เด็ก ผู้สูงอายุ และสัตว์เลี้ยงตามที่ต้องการ" : "Accessibility, health, child, older-adult, and pet needs can be supported"}</li>
                <li>{th ? "ทราบว่าต้องนำเอกสาร ยา น้ำ อาหาร และของใช้ใดไป" : "You know which documents, medicine, water, food, and supplies to bring"}</li>
              </ol>
            </article>
            <EvidenceNotice tone="caution" title={th ? "อย่าเดินทางตามหมุดจากข้อมูลเปิดเพียงอย่างเดียว" : "Do not travel based only on an open-data map marker"}>
              {th ? "ปฏิบัติตามคำแนะนำของ ปภ. และหน่วยงานท้องถิ่น และยืนยันจุดหมายก่อนออกเดินทาง" : "Follow DDPM and local-authority guidance, and confirm the destination before leaving."}
            </EvidenceNotice>
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
              onSelectNoNeedsApply={householdPlan.selectNoNeedsApply}
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
              <article className="card public-about-card public-about-capabilities"><h2><span aria-hidden="true">✓</span>{th ? "สิ่งที่มีให้" : "What this provides"}</h2><ul><li>{th ? "แสดงขอบเขตพื้นที่แม่สายและบริบทอุทกภัยเดือนกันยายน 2567" : "Shows Mae Sai area boundaries and September 2024 flood context"}</li><li>{th ? "แสดงจุดเน้นจากแบบจำลองเพื่อช่วยจัดลำดับการตรวจสอบในพื้นที่" : "Shows modelled planning priorities to organize local checks"}</li><li>{th ? "เก็บแผนครัวเรือนและสำเนาข้อมูลประวัติศาสตร์ไว้ในอุปกรณ์" : "Keeps the household plan and a historical information copy on the device"}</li></ul></article>
              <article className="card blocked-card public-about-card"><h2><span aria-hidden="true">×</span>{th ? "สิ่งที่ต้องยืนยัน" : "What must be confirmed"}</h2><ul><li>{th ? "คำเตือนและคำแนะนำอพยพปัจจุบันจากหน่วยงานที่รับผิดชอบ" : "Current warnings and evacuation guidance from responsible authorities"}</li><li>{th ? "สภาพถนน การเปิดให้บริการ บทบาท และความจุของสถานที่" : "Current road conditions, facility operation, role, and capacity"}</li><li>{hasDecisionEligibleModel ? (th ? "ผลแบบจำลองไม่ใช่คำสั่งฉุกเฉิน โปรดติดตามประกาศทางการ" : "Model results are not emergency directions; follow official alerts") : (th ? "ผลลัพธ์ใช้จัดลำดับการตรวจสอบ ไม่ใช่การยืนยันอันตรายปัจจุบัน" : "Results prioritize checks; they do not confirm current danger")}</li></ul></article>
            </div>
            <article className="card method-card"><h2>{th ? "วิธีวิเคราะห์การเข้าถึง" : "Access method"}</h2><p>{th ? "เอนจินเปรียบเทียบเวลาเดินทางสั้นที่สุดไปยังสถานที่ที่เลือกภายใต้เครือข่ายปกติและเครือข่ายที่ถูกรบกวน ที่เกณฑ์ 15/30/60 นาที ผลลัพธ์เป็นแบบจำลองประวัติศาสตร์และไม่ได้คำนวณความจุของสถานที่" : "The engine compares shortest travel time to selected facilities under normal and disrupted networks at 15/30/60-minute thresholds. Results are historical model outputs and are not facility-capacity aware."}</p></article>
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
