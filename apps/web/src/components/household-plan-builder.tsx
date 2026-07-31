"use client";

import { useState } from "react";

import {
  HOUSEHOLD_NEEDS,
  HOUSEHOLD_NEED_ACTIONS,
  HOUSEHOLD_NEED_COUNT_MAX,
  HOUSEHOLD_PLAN_ITEMS,
  buildHouseholdPlanText,
  canReviewHouseholdPlan,
  countCompletedPlanItems,
  householdNeedCountLabel,
  isCountableNeed,
  selectedHouseholdNeeds,
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
  onSetNeedCount: (needId: HouseholdNeedId, count: number) => void;
  onSelectNoNeedsApply: () => void;
  onMarkReviewed: () => void;
  onResetChecklist: () => void;
  onClearPlan: () => void;
}

type PlanStepId = 1 | 2 | 3 | 4;

const PLAN_STEPS: Array<{ id: PlanStepId; en: string; th: string }> = [
  { id: 1, en: "Household needs", th: "ความต้องการครัวเรือน" },
  { id: 2, en: "Tailored actions", th: "การดำเนินการเฉพาะ" },
  { id: 3, en: "Core actions", th: "รายการพื้นฐาน" },
  { id: 4, en: "Review & keep", th: "ทบทวนและเก็บสำเนา" },
];

/**
 * "done" once the step's own record exists, "current" for the first step still
 * outstanding, "pending" after that. It reports what the reader has recorded,
 * never whether the household is prepared.
 */
function planStepState(
  id: PlanStepId,
  currentStep: PlanStepId,
  done: boolean,
): "done" | "current" | "pending" {
  if (done) return "done";
  return id === currentStep ? "current" : "pending";
}

function formatPlanTimestamp(timestamp: string | null, language: Language, fallback: string): string {
  if (!timestamp) return fallback;
  return new Intl.DateTimeFormat(language === "th" ? "th-TH" : "en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Bangkok",
  }).format(new Date(timestamp));
}

export function HouseholdPlanBuilder({
  language,
  plan,
  areaNameTh,
  areaNameEn,
  onToggleItem,
  onToggleNeed,
  onSetNeedCount,
  onSelectNoNeedsApply,
  onMarkReviewed,
  onResetChecklist,
  onClearPlan,
}: HouseholdPlanBuilderProps) {
  const [confirmingClear, setConfirmingClear] = useState(false);
  const th = language === "th";
  const completed = countCompletedPlanItems(plan);
  const total = HOUSEHOLD_PLAN_ITEMS.length;
  const selectedNeedIds = selectedHouseholdNeeds(plan);
  const canReview = canReviewHouseholdPlan(plan);
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

  const reviewedLabel = formatPlanTimestamp(
    plan.last_reviewed_at,
    language,
    th ? "ยังไม่ได้ทบทวน" : "Not reviewed yet",
  );
  const savedLabel = formatPlanTimestamp(
    plan.last_saved_at,
    language,
    th ? "ยังไม่มีการเปลี่ยนแปลงที่บันทึก" : "No saved changes yet",
  );
  const needsStatus = plan.needs_review_state === "selected"
    ? (th ? `เลือกแล้ว ${selectedNeedIds.length} ข้อ` : `${selectedNeedIds.length} selected`)
    : plan.needs_review_state === "none_apply"
      ? (th ? "ยืนยันว่าไม่มีข้อใดใช้กับครัวเรือน" : "Confirmed: none apply")
      : (th ? "ยังไม่ได้ทบทวน" : "Not reviewed");

  const stepDone: Record<PlanStepId, boolean> = {
    1: plan.needs_review_state !== "not_reviewed",
    2: plan.needs_review_state !== "not_reviewed",
    3: total > 0 && completed === total,
    4: Boolean(plan.last_reviewed_at),
  };
  const currentStep = (PLAN_STEPS.find(({ id }) => !stepDone[id])?.id ?? 4) as PlanStepId;

  return (
    <div className="household-plan-builder" id="household-plan-builder" data-plan-completed={completed} data-needs-review-state={plan.needs_review_state}>
      <section className="card household-plan-summary" aria-labelledby="household-plan-title">
        <h2 id="household-plan-title">{th ? "แผนเตรียมพร้อมของครัวเรือน" : "My household preparedness plan"}</h2>

        {/* Where the plan stands across the four steps below. */}
        <ol className="plan-step-track" aria-label={th ? "ความคืบหน้าของแผน" : "Plan progress"}>
          {PLAN_STEPS.map((step) => {
            const state = planStepState(step.id, currentStep, stepDone[step.id]);
            return (
              <li key={step.id} data-state={state}>
                <span className="plan-step-track__dot" aria-hidden="true">
                  {state === "done"
                    ? (
                      <svg viewBox="0 0 24 24">
                        <path
                          d="m5 12.5 4.2 4.2L19 7"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="2.8"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    )
                    : step.id}
                </span>
                <span className="plan-step-track__label">{step[language]}</span>
              </li>
            );
          })}
        </ol>

        <div className="plan-status-grid" aria-label={th ? "สถานะแผนแยกตามส่วน" : "Plan status by section"}>
          <article>
            <span>{th ? "ความต้องการครัวเรือน" : "Household needs"}</span>
            <b>{needsStatus}</b>
          </article>
          <article>
            <span>{th ? "การทบทวนแผน" : "Plan review"}</span>
            <b>{plan.last_reviewed_at ? (th ? "บันทึกแล้ว" : "Recorded") : (th ? "ยังไม่ได้บันทึก" : "Not recorded")}</b>
          </article>
          <article>
            <span>{th ? "บันทึกล่าสุด" : "Last saved"}</span>
            <b>{savedLabel}</b>
          </article>
        </div>
      </section>

      <section className="card household-needs" aria-labelledby="household-needs-title">
        <h2 id="household-needs-title">
          <span className="plan-step-number">{th ? "ขั้นที่ 1" : "Step 1"}</span>
          {th ? "ทบทวนความต้องการของครัวเรือน" : "Review household needs"}
        </h2>
        <p className="plan-privacy-note">
          {th
            ? "เลือกเฉพาะสิ่งที่ใช้กับครัวเรือน หรือยืนยันว่าไม่มีข้อใดใช้ ระบบไม่ขอที่อยู่ บัญชี ชื่อบุคคล หรือการวินิจฉัยทางการแพทย์"
            : "Select what applies, or explicitly confirm that none apply. The app does not ask for an address, account, names, or a medical diagnosis."}
        </p>
        <div className="household-need-options" role="group" aria-label={th ? "ความต้องการที่ต้องนำมาวางแผน" : "Needs to account for"}>
          {HOUSEHOLD_NEEDS.map((need) => {
            const selected = plan.needs[need.id];
            const count = plan.need_counts[need.id] ?? 1;
            const countable = isCountableNeed(need.id);
            return (
              <div className="household-need-option" key={need.id}>
                <button
                  type="button"
                  aria-pressed={selected}
                  className={selected ? "selected" : ""}
                  onClick={() => onToggleNeed(need.id)}
                >
                  <span aria-hidden="true">{selected ? "✓" : "+"}</span>
                  {need[language]}
                </button>
                {/* How many people this need covers, so plans elsewhere can say
                    "2 children" instead of just naming the need. */}
                {selected && countable && (
                  <div className="household-need-count">
                    <button
                      type="button"
                      disabled={count <= 1}
                      aria-label={th ? `ลดจำนวน ${need[language]}` : `Fewer: ${need[language]}`}
                      onClick={() => onSetNeedCount(need.id, count - 1)}
                    >
                      −
                    </button>
                    <output aria-live="polite">
                      {householdNeedCountLabel(need.id, count, language)}
                    </output>
                    <button
                      type="button"
                      disabled={count >= HOUSEHOLD_NEED_COUNT_MAX}
                      aria-label={th ? `เพิ่มจำนวน ${need[language]}` : `More: ${need[language]}`}
                      onClick={() => onSetNeedCount(need.id, count + 1)}
                    >
                      +
                    </button>
                  </div>
                )}
              </div>
            );
          })}
          <button
            type="button"
            aria-pressed={plan.needs_review_state === "none_apply"}
            className={`household-none-apply${plan.needs_review_state === "none_apply" ? " selected" : ""}`}
            onClick={onSelectNoNeedsApply}
          >
            <span aria-hidden="true">{plan.needs_review_state === "none_apply" ? "✓" : "—"}</span>
            {th ? "ไม่มีข้อใดในรายการนี้ที่ใช้กับครัวเรือน" : "None of these apply to my household"}
          </button>
        </div>
      </section>

      <section className="card tailored-plan-actions" aria-labelledby="tailored-plan-actions-title">
        <h2 id="tailored-plan-actions-title">
          <span className="plan-step-number">{th ? "ขั้นที่ 2" : "Step 2"}</span>
          {th ? "การดำเนินการตามความต้องการที่เลือก" : "Actions for the needs you selected"}
        </h2>
        {selectedNeedIds.length > 0 ? (
          <ul>
            {selectedNeedIds.map((needId) => <li key={needId}>{HOUSEHOLD_NEED_ACTIONS[needId][language]}</li>)}
          </ul>
        ) : (
          <p>{plan.needs_review_state === "none_apply"
            ? (th ? "คุณยืนยันว่าไม่มีความต้องการเพิ่มเติมจากรายการนี้ ดำเนินการรายการพื้นฐานต่อไป" : "You confirmed that none of these additional needs apply. Continue with the core actions.")
            : (th ? "ทบทวนความต้องการด้านบนเพื่อสร้างรายการดำเนินการที่เหมาะกับครัวเรือน" : "Review the needs above to create actions tailored to your household.")}</p>
        )}
      </section>

      <section aria-labelledby="household-checklist-title">
        <div className="section-heading">
          <div>
            <h2 id="household-checklist-title">
              <span className="plan-step-number">{th ? "ขั้นที่ 3" : "Step 3"}</span>
              {th ? "ทำรายการพื้นฐานร่วมกัน" : "Complete the core actions together"}
            </h2>
          </div>
          <button type="button" className="text-action" onClick={onResetChecklist} disabled={completed === 0}>
            {th ? "รีเซ็ตรายการ" : "Reset actions"}
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
          <h2 id="plan-review-title">
            <span className="plan-step-number">{th ? "ขั้นที่ 4" : "Step 4"}</span>
            {th ? "ทบทวน เก็บสำเนา และยืนยันกับท้องถิ่น" : "Review, keep a copy, and confirm locally"}
          </h2>
          <p>{th ? `ทบทวนล่าสุด: ${reviewedLabel}` : `Last reviewed: ${reviewedLabel}`}</p>
          <p className="seasonal-review-reminder">{th
            ? "ทบทวนก่อนฤดูฝน และเมื่อสมาชิก ยา การเดินทาง หรือจุดนัดพบเปลี่ยนแปลง"
            : "Review before the rainy season and whenever household members, medicine, transport, or meeting places change."}</p>
          {!canReview && <p id="plan-review-requirement" className="plan-review-requirement">{th
            ? "เลือกความต้องการอย่างน้อยหนึ่งข้อ หรือยืนยันว่าไม่มีข้อใดใช้ ก่อนบันทึกการทบทวน"
            : "Select at least one household need or confirm that none apply before recording a review."}</p>}
        </div>
        <div className="plan-review-actions">
          <button
            type="button"
            className="primary-link"
            onClick={onMarkReviewed}
            disabled={!canReview}
            aria-describedby={!canReview ? "plan-review-requirement" : undefined}
          >
            {th ? "บันทึกว่าทบทวนแล้ว" : "Record plan review"}
          </button>
          <button type="button" onClick={downloadPlan}>{th ? "ดาวน์โหลดแผนสองภาษา" : "Download bilingual plan"}</button>
          <button type="button" onClick={printPlan}>{th ? "พิมพ์แผนสองภาษา" : "Print bilingual plan"}</button>
          <button type="button" className="danger-text-action" onClick={() => setConfirmingClear(true)}>
            {th ? "ล้างแผนจากอุปกรณ์นี้" : "Clear plan from this device"}
          </button>
        </div>
        {confirmingClear && (
          <div className="clear-plan-confirmation" role="alert">
            <p>{th ? "ล้างพื้นที่ การเลือก และรายการทั้งหมดจากอุปกรณ์นี้หรือไม่?" : "Clear the area, selections, and actions from this device?"}</p>
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
    </div>
  );
}
