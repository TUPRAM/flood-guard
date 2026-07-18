"use client";

import { useState } from "react";

import {
  HOUSEHOLD_NEEDS,
  HOUSEHOLD_PLAN_ITEMS,
  buildHouseholdPlanText,
  countCompletedPlanItems,
  type HouseholdNeedId,
  type HouseholdPlan,
  type HouseholdPlanItemId,
} from "@/lib/household-plan";
import type { Language } from "@/lib/types";

interface HouseholdPlanBuilderProps {
  language: Language;
  plan: HouseholdPlan;
  areaNameTh: string;
  areaNameEn: string;
  onToggleItem: (itemId: HouseholdPlanItemId) => void;
  onToggleNeed: (needId: HouseholdNeedId) => void;
  onMarkReviewed: () => void;
  onResetChecklist: () => void;
  onClearPlan: () => void;
}

export function HouseholdPlanBuilder({
  language,
  plan,
  areaNameTh,
  areaNameEn,
  onToggleItem,
  onToggleNeed,
  onMarkReviewed,
  onResetChecklist,
  onClearPlan,
}: HouseholdPlanBuilderProps) {
  const [confirmingClear, setConfirmingClear] = useState(false);
  const th = language === "th";
  const completed = countCompletedPlanItems(plan);
  const total = HOUSEHOLD_PLAN_ITEMS.length;
  const progress = Math.round((completed / total) * 100);
  const bilingualPlanText = () => buildHouseholdPlanText(plan, areaNameTh, areaNameEn);

  const downloadPlan = () => {
    const url = URL.createObjectURL(new Blob([bilingualPlanText()], { type: "text/plain;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "floodguard-household-plan-bilingual.txt";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  const printPlan = () => {
    const frame = document.createElement("iframe");
    frame.title = th ? "สำเนาแผนครัวเรือนสองภาษา" : "Bilingual household plan copy";
    frame.setAttribute("aria-hidden", "true");
    frame.style.position = "fixed";
    frame.style.width = "1px";
    frame.style.height = "1px";
    frame.style.opacity = "0";
    frame.style.pointerEvents = "none";
    document.body.appendChild(frame);

    const printDocument = frame.contentDocument;
    const printWindow = frame.contentWindow;
    if (!printDocument || !printWindow) {
      frame.remove();
      window.print();
      return;
    }

    const copy = printDocument.createElement("pre");
    copy.textContent = bilingualPlanText();
    copy.style.fontFamily = "system-ui, sans-serif";
    copy.style.fontSize = "12pt";
    copy.style.lineHeight = "1.55";
    copy.style.whiteSpace = "pre-wrap";
    copy.style.margin = "16mm";
    printDocument.body.appendChild(copy);
    printWindow.addEventListener("afterprint", () => frame.remove(), { once: true });
    printWindow.focus();
    printWindow.print();
  };

  const reviewedLabel = plan.last_reviewed_at
    ? new Intl.DateTimeFormat(th ? "th-TH" : "en-GB", {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: "Asia/Bangkok",
    }).format(new Date(plan.last_reviewed_at))
    : (th ? "ยังไม่ได้ทบทวน" : "Not reviewed yet");

  return (
    <div className="household-plan-builder" id="household-plan-builder" data-plan-completed={completed}>
      <section className="card household-plan-summary" aria-labelledby="household-plan-title">
        <div>
          <p className="eyebrow">{th ? "เก็บไว้ในอุปกรณ์นี้เท่านั้น" : "Stored only on this device"}</p>
          <h2 id="household-plan-title">{th ? "แผนเตรียมพร้อมของครัวเรือน" : "My household preparedness plan"}</h2>
          <p>
            {th
              ? `พื้นที่วางแผน: ${areaNameTh || "ยังไม่มีพื้นที่"} · ไม่ใช่ตำแหน่งที่อยู่ที่แน่นอน`
              : `Planning area: ${areaNameEn || "No area available"} · not an exact household location`}
          </p>
        </div>
        <div className="plan-progress" aria-label={th ? `ทำเสร็จ ${completed} จาก ${total} รายการ` : `${completed} of ${total} items complete`}>
          <b>{completed}/{total}</b>
          <progress value={completed} max={total}>{progress}%</progress>
          <small>{th ? "รายการเสร็จแล้ว" : "items complete"}</small>
        </div>
      </section>

      <section className="card household-needs" aria-labelledby="household-needs-title">
        <p className="eyebrow">{th ? "ขั้นที่ 1" : "Step 1"}</p>
        <h2 id="household-needs-title">{th ? "สิ่งที่แผนครัวเรือนต้องคำนึงถึง" : "What should this household plan account for?"}</h2>
        <p className="plan-privacy-note">
          {th
            ? "เลือกได้เท่าที่จำเป็น ระบบไม่ขอที่อยู่ บัญชีผู้ใช้ ชื่อบุคคล หรือการวินิจฉัยทางการแพทย์"
            : "Select only what is useful. The app does not ask for an address, account, names, or a medical diagnosis."}
        </p>
        <div className="household-need-options">
          {HOUSEHOLD_NEEDS.map((need) => (
            <button
              key={need.id}
              type="button"
              aria-pressed={plan.needs[need.id]}
              className={plan.needs[need.id] ? "selected" : ""}
              onClick={() => onToggleNeed(need.id)}
            >
              <span aria-hidden="true">{plan.needs[need.id] ? "✓" : "+"}</span>
              {need[language]}
            </button>
          ))}
        </div>
      </section>

      <section aria-labelledby="household-checklist-title">
        <div className="section-heading">
          <div>
            <p className="eyebrow">{th ? "ขั้นที่ 2" : "Step 2"}</p>
            <h2 id="household-checklist-title">{th ? "ทำรายการเตรียมพร้อมร่วมกัน" : "Complete the plan together"}</h2>
          </div>
          <button type="button" className="text-action" onClick={onResetChecklist} disabled={completed === 0}>
            {th ? "รีเซ็ตรายการ" : "Reset checklist"}
          </button>
        </div>
        <div className="checklist-grid">
          {HOUSEHOLD_PLAN_ITEMS.map((item, index) => (
            <label className="check-item" key={item.id}>
              <input
                type="checkbox"
                checked={plan.checklist[item.id]}
                onChange={() => onToggleItem(item.id)}
              />
              <span><b>{String(index + 1).padStart(2, "0")}</b>{item[language]}</span>
            </label>
          ))}
        </div>
      </section>

      <section className="card plan-review-card" aria-labelledby="plan-review-title">
        <div>
          <p className="eyebrow">{th ? "ขั้นที่ 3" : "Step 3"}</p>
          <h2 id="plan-review-title">{th ? "ทบทวน พิมพ์ และยืนยันกับท้องถิ่น" : "Review, keep a copy, and confirm locally"}</h2>
          <p>{th ? `ทบทวนล่าสุด: ${reviewedLabel}` : `Last reviewed: ${reviewedLabel}`}</p>
        </div>
        <div className="plan-review-actions">
          <button type="button" className="primary-link" onClick={onMarkReviewed}>
            {th ? "ทำเครื่องหมายว่าทบทวนแล้ว" : "Mark as reviewed"}
          </button>
          <button type="button" onClick={downloadPlan}>{th ? "ดาวน์โหลดสองภาษา" : "Download bilingual plan"}</button>
          <button type="button" onClick={printPlan}>{th ? "พิมพ์แผนสองภาษา" : "Print bilingual plan"}</button>
          <button type="button" className="danger-text-action" onClick={() => setConfirmingClear(true)}>
            {th ? "ล้างแผนจากอุปกรณ์นี้" : "Clear plan from this device"}
          </button>
        </div>
        {confirmingClear && (
          <div className="clear-plan-confirmation" role="alert">
            <p>{th ? "ล้างพื้นที่ การเลือก และรายการทั้งหมดจากอุปกรณ์นี้หรือไม่?" : "Clear the area, selections, and checklist from this device?"}</p>
            <div>
              <button type="button" onClick={() => setConfirmingClear(false)}>{th ? "ยกเลิก" : "Cancel"}</button>
              <button
                type="button"
                className="danger-text-action"
                onClick={() => {
                  onClearPlan();
                  setConfirmingClear(false);
                }}
              >
                {th ? "ยืนยันการล้าง" : "Confirm clear"}
              </button>
            </div>
          </div>
        )}
      </section>

      <aside className="card plan-safety-note">
        <b>{th ? "ไม่ใช่คำสั่งฉุกเฉิน" : "Not emergency direction"}</b>
        <p>
          {th
            ? "แผนนี้ไม่คำนวณเส้นทางปลอดภัย ไม่ติดตามตำแหน่ง และไม่แทนที่ประกาศของ ปภ. กรมอุตุนิยมวิทยา หรือหน่วยงานท้องถิ่น"
            : "This plan does not calculate a safe route, track your location, or replace notices from DDPM, TMD, or local authorities."}
        </p>
      </aside>
    </div>
  );
}
