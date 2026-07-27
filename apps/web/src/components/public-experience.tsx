"use client";

import { useEffect, useRef, useState } from "react";

import { HouseholdPlanBuilder } from "@/components/household-plan-builder";
import { PublicAppHeader } from "@/components/public-app-header";
import { PublicAppIcon, type PublicAppIconName } from "@/components/public-app-icon";
import { PublicHomePage } from "@/components/public-home-page";
import { PublicReportPage } from "@/components/public-report-page";
import { PublicShelterPage } from "@/components/public-shelter-page";
import { PublicSosPage } from "@/components/public-sos-page";
import { HOUSEHOLD_NEEDS, countCompletedPlanItems } from "@/lib/household-plan";
import type { PublicMapLocation } from "@/lib/public-location";
import type { FeatureCollection } from "@/lib/types";
import { useHouseholdPlan } from "@/lib/use-household-plan";
import { useLanguage } from "@/lib/use-language";
import { usePublicFloodGuardData } from "@/lib/use-public-floodguard-data";

type PublicPage = "home" | "report" | "shelter" | "prepare" | "sos";

const PAGE_LABELS: Record<PublicPage, {
  th: string;
  en: string;
  icon: PublicAppIconName;
}> = {
  home: { th: "หน้าแรก", en: "Home", icon: "home" },
  report: { th: "รายงาน", en: "Report", icon: "report" },
  shelter: { th: "ที่พักพิง", en: "Shelter", icon: "shelter" },
  prepare: { th: "เตรียมพร้อม", en: "Prepare", icon: "prepare" },
  sos: { th: "SOS", en: "SOS", icon: "sos" },
};

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

export function projectPublicFacilityFeatures(
  features: FeatureCollection,
): FeatureCollection {
  return {
    ...features,
    name: `${features.name}_public_confirmed`,
    features: features.features.filter((feature) => {
      const verification = String(
        feature.properties.verification_status ?? "",
      ).toLowerCase();
      const candidateStatus = String(
        feature.properties.candidate_status ?? "",
      ).toLowerCase();
      const emergencyRole = String(
        feature.properties.emergency_role ?? "",
      ).toLowerCase();
      const isShelter = String(
        feature.properties.facility_type ?? "",
      ).toLowerCase().includes("shelter");
      const hasConfirmedEmergencyRole = CONFIRMED_PUBLIC_EMERGENCY_ROLES.has(
        emergencyRole,
      );
      return CONFIRMED_PUBLIC_FACILITY_STATES.has(verification)
        && !candidateStatus.includes("candidate")
        && (!isShelter || hasConfirmedEmergencyRole);
    }),
  };
}

export function PublicExperience() {
  const data = usePublicFloodGuardData();
  const [language, setLanguage] = useLanguage("th");
  const [page, setPage] = useState<PublicPage>("home");
  const [homeLocation, setHomeLocation] = useState<PublicMapLocation>();
  const [locationChoiceHandled, setLocationChoiceHandled] = useState(false);
  const contentRef = useRef<HTMLElement>(null);
  const {
    plan,
    selectPlanningArea,
    toggleChecklistItem,
    toggleNeed,
    selectNoNeedsApply,
    markReviewed,
    resetChecklist,
    clearPlan,
  } = useHouseholdPlan("");
  const th = language === "th";
  const selectedArea = data.publicAreas.find(
    (area) => area.area_id === plan.planning_area_id,
  );
  const selectedAreaName = selectedArea
    ? (th ? selectedArea.area_name_th : selectedArea.area_name_en)
    : "";
  const selectedNeedCount = HOUSEHOLD_NEEDS.filter(
    (need) => plan.needs[need.id],
  ).length;
  const needsSummary = plan.needs_review_state === "selected"
    ? (th ? `เลือกแล้ว ${selectedNeedCount} ข้อ` : `${selectedNeedCount} selected`)
    : plan.needs_review_state === "none_apply"
      ? (th ? "ยืนยันว่าไม่มีข้อใดใช้" : "None apply")
      : (th ? "ยังไม่ได้ทบทวน" : "Not reviewed");
  const completedItems = countCompletedPlanItems(plan);
  const reportArea = selectedArea
    ? {
        area_id: selectedArea.area_id,
        area_name_th: selectedArea.area_name_th,
        area_name_en: selectedArea.area_name_en,
      }
    : undefined;

  useEffect(() => {
    if (
      data.publicAreas.length > 0
      && plan.planning_area_id
      && !selectedArea
    ) {
      selectPlanningArea("");
    }
  }, [
    data.publicAreas.length,
    plan.planning_area_id,
    selectPlanningArea,
    selectedArea,
  ]);

  useEffect(() => {
    contentRef.current?.scrollTo({ top: 0, behavior: "auto" });
  }, [page]);

  const navigate = (nextPage: PublicPage) => {
    setPage(nextPage);
  };

  const prepareAreaNameTh = selectedArea?.area_name_th ?? "";
  const prepareAreaNameEn = selectedArea?.area_name_en ?? "";
  const contentClassName = [
    "public-app-content",
    page === "home" ? "is-home" : "is-scrollable",
  ].join(" ");

  return (
    <main className="public-page public-app-shell" lang={language}>
      <PublicAppHeader
        language={language}
        onLanguageChange={setLanguage}
        planningAreaName={selectedAreaName}
        needsSummary={needsSummary}
        onNavigatePrepare={() => navigate("prepare")}
        onNavigateSos={() => navigate("sos")}
      />

      <section
        ref={contentRef}
        id="public-active-panel"
        className={contentClassName}
        aria-live="polite"
        aria-labelledby={`public-tab-${page}`}
        data-public-page={page}
      >
        {page === "home" && (
          <PublicHomePage
            language={language}
            data={data}
            selectedAreaId={selectedArea?.area_id ?? ""}
            onSelectArea={selectPlanningArea}
            location={homeLocation}
            locationChoiceHandled={locationChoiceHandled}
            onLocationChange={setHomeLocation}
            onLocationChoiceHandled={() => setLocationChoiceHandled(true)}
          />
        )}

        {page === "report" && (
          <PublicReportPage
            language={language}
            selectedArea={reportArea}
          />
        )}

        {page === "shelter" && (
          <PublicShelterPage
            language={language}
            selectedAreaName={selectedAreaName}
            plan={plan}
            onNavigatePrepare={() => navigate("prepare")}
          />
        )}

        {page === "prepare" && (
          <section className="public-prepare-view" aria-labelledby="public-prepare-title">
            <header className="public-page-heading">
              <p className="eyebrow">{th ? "แผนครัวเรือน" : "HOUSEHOLD PLAN"}</p>
              <h1 id="public-prepare-title">
                {th ? "สร้างและทบทวนแผนเตรียมพร้อม" : "Build and review my preparedness plan"}
              </h1>
              <p>
                {th
                  ? "ทำตามขั้นที่ 1–4 และเก็บสำเนาไว้ในอุปกรณ์นี้"
                  : "Complete steps 1–4 and keep a copy on this device."}
              </p>
            </header>

            <section className="public-prepare-area-selector" aria-labelledby="public-prepare-area-title">
              <div>
                <p className="eyebrow">{th ? "พื้นที่วางแผน" : "PLANNING AREA"}</p>
                <h2 id="public-prepare-area-title">
                  {th ? "เลือกพื้นที่กว้าง" : "Choose a broad area"}
                </h2>
                <p>
                  {th
                    ? "ใช้เฉพาะชื่อพื้นที่กว้าง ไม่ใช่ตำแหน่งบ้านที่แน่นอน"
                    : "Use a broad area name, not an exact household location."}
                </p>
              </div>
              <label htmlFor="public-prepare-area-select">
                <span className="sr-only">
                  {th ? "พื้นที่วางแผน" : "Planning area"}
                </span>
                <select
                  id="public-prepare-area-select"
                  value={selectedArea?.area_id ?? ""}
                  onChange={(event) => selectPlanningArea(event.target.value)}
                >
                  <option value="">
                    {th ? "เลือกพื้นที่" : "Choose an area"}
                  </option>
                  {data.publicAreas.map((area) => (
                    <option key={area.area_id} value={area.area_id}>
                      {th ? area.area_name_th : area.area_name_en}
                    </option>
                  ))}
                </select>
              </label>
            </section>

            <HouseholdPlanBuilder
              language={language}
              plan={plan}
              areaNameTh={prepareAreaNameTh}
              areaNameEn={prepareAreaNameEn}
              onToggleItem={toggleChecklistItem}
              onToggleNeed={toggleNeed}
              onSelectNoNeedsApply={selectNoNeedsApply}
              onMarkReviewed={markReviewed}
              onResetChecklist={resetChecklist}
              onClearPlan={clearPlan}
            />

            <aside className="public-prepare-safety-note">
              <PublicAppIcon name="hazard" />
              <div>
                <strong>{th ? "ไม่ใช่คำสั่งฉุกเฉิน" : "Not emergency direction"}</strong>
                <p>
                  {th
                    ? "แผนนี้ไม่คำนวณเส้นทางที่ปลอดภัย ไม่ติดตามตำแหน่ง และไม่แทนที่คำแนะนำจาก ปภ. กรมอุตุนิยมวิทยา หรือหน่วยงานท้องถิ่น"
                    : "This plan does not calculate a safe route, track your location, or replace DDPM, TMD, or local-authority instructions."}
                </p>
              </div>
            </aside>
          </section>
        )}

        {page === "sos" && (
          <PublicSosPage
            language={language}
            hotlines={data.hotlines}
            plan={plan}
            selectedAreaName={selectedAreaName}
          />
        )}
      </section>

      <nav
        className="public-bottom-nav"
        aria-label={th ? "การนำทางหลัก" : "Main navigation"}
      >
        {(Object.keys(PAGE_LABELS) as PublicPage[]).map((key) => {
          const item = PAGE_LABELS[key];
          const active = page === key;
          return (
            <button
              key={key}
              id={`public-tab-${key}`}
              type="button"
              className={[
                active ? "active" : "",
                key === "sos" ? "sos" : "",
              ].filter(Boolean).join(" ")}
              aria-controls="public-active-panel"
              aria-pressed={active}
              onClick={() => navigate(key)}
            >
              <span className="public-bottom-nav-icon">
                <PublicAppIcon name={item.icon} />
              </span>
              <span>{item[language]}</span>
              {key === "prepare" && completedItems > 0 && (
                <small aria-label={th ? `เสร็จแล้ว ${completedItems} รายการ` : `${completedItems} actions complete`}>
                  {completedItems}
                </small>
              )}
            </button>
          );
        })}
      </nav>
    </main>
  );
}
