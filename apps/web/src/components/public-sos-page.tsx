"use client";

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type PointerEvent,
} from "react";

import {
  HOUSEHOLD_NEEDS,
  type HouseholdPlan,
} from "@/lib/household-plan";
import type { Hotline, Language } from "@/lib/types";

interface PublicSosPageProps {
  language: Language;
  hotlines: Hotline[];
  plan: HouseholdPlan;
  selectedAreaName: string;
}

const HOLD_DURATION_MS = 3_000;

const OFFICIAL_HOTLINES: Hotline[] = [
  {
    number: "1784",
    label_th: "สายด่วนนิรภัย ปภ.",
    label_en: "DDPM disaster hotline",
    href: "tel:1784",
    source_url: "https://www.disaster.go.th/home",
  },
  {
    number: "1669",
    label_th: "การแพทย์ฉุกเฉิน",
    label_en: "Emergency medical service",
    href: "tel:1669",
    source_url: "https://www.niems.go.th/1/SubWebsite/?id=1096",
  },
  {
    number: "191",
    label_th: "เหตุด่วนเหตุร้าย",
    label_en: "Police emergency",
    href: "tel:191",
    source_url: "https://royalthaipolice.go.th/",
  },
];

export function PublicSosPage({
  language,
  hotlines,
  plan,
  selectedAreaName,
}: PublicSosPageProps) {
  const th = language === "th";
  const [holding, setHolding] = useState(false);
  const [holdProgress, setHoldProgress] = useState(0);
  const [actionsVisible, setActionsVisible] = useState(false);
  const holdingRef = useRef(false);
  const completedRef = useRef(false);
  const holdIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const holdTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const selectedNeeds = useMemo(
    () => HOUSEHOLD_NEEDS.filter(({ id }) => plan.needs[id]),
    [plan.needs],
  );
  const hotlineActions = useMemo(
    () => OFFICIAL_HOTLINES.map((fallback) => {
      const provided = hotlines.find(({ number }) => number === fallback.number);
      return provided
        ? {
          ...fallback,
          label_th: provided.label_th,
          label_en: provided.label_en,
          source_url: provided.source_url,
        }
        : fallback;
    }),
    [hotlines],
  );
  const broadArea = selectedAreaName.trim()
    || (th ? "ไม่ได้เลือกพื้นที่กว้าง" : "No broad area selected");
  const needsText = selectedNeeds.length > 0
    ? selectedNeeds.map((need) => need[language]).join(", ")
    : (th ? "ไม่มีความต้องการที่บันทึกไว้" : "No household needs recorded");
  const smsBody = th
    ? [
      "SOS FloodGuard",
      `พื้นที่กว้าง: ${broadArea}`,
      `ความต้องการของครัวเรือน: ${needsText}`,
      "โปรดโทรกลับเพื่อยืนยันรายละเอียด",
    ].join("\n")
    : [
      "SOS FloodGuard",
      `Broad planning area: ${broadArea}`,
      `Household needs: ${needsText}`,
      "Please call back to confirm details.",
    ].join("\n");
  const smsHref = `sms:1784?body=${encodeURIComponent(smsBody)}`;

  useEffect(() => {
    return () => {
      if (holdIntervalRef.current) clearInterval(holdIntervalRef.current);
      if (holdTimeoutRef.current) clearTimeout(holdTimeoutRef.current);
      holdingRef.current = false;
    };
  }, []);

  const clearHoldTimers = () => {
    if (holdIntervalRef.current) {
      clearInterval(holdIntervalRef.current);
      holdIntervalRef.current = null;
    }
    if (holdTimeoutRef.current) {
      clearTimeout(holdTimeoutRef.current);
      holdTimeoutRef.current = null;
    }
  };

  const completeHold = () => {
    clearHoldTimers();
    holdingRef.current = false;
    completedRef.current = true;
    setHolding(false);
    setHoldProgress(100);
    setActionsVisible(true);
  };

  const startHold = () => {
    if (holdingRef.current || completedRef.current) return;

    clearHoldTimers();
    const startedAt = Date.now();
    holdingRef.current = true;
    setHolding(true);
    setHoldProgress(0);

    holdIntervalRef.current = setInterval(() => {
      const elapsed = Date.now() - startedAt;
      setHoldProgress(Math.min(99, Math.round((elapsed / HOLD_DURATION_MS) * 100)));
    }, 50);
    holdTimeoutRef.current = setTimeout(completeHold, HOLD_DURATION_MS);
  };

  const cancelHold = () => {
    if (!holdingRef.current || completedRef.current) return;
    clearHoldTimers();
    holdingRef.current = false;
    setHolding(false);
    setHoldProgress(0);
  };

  const handlePointerDown = (event: PointerEvent<HTMLButtonElement>) => {
    if (event.button !== 0) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    startHold();
  };

  const handlePointerEnd = (event: PointerEvent<HTMLButtonElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    cancelHold();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key !== " " && event.key !== "Enter") return;
    event.preventDefault();
    if (!event.repeat) startHold();
  };

  const handleKeyUp = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key !== " " && event.key !== "Enter") return;
    event.preventDefault();
    cancelHold();
  };

  const holdStyle = {
    "--public-sos-hold-progress": `${holdProgress}%`,
  } as CSSProperties;

  return (
    <section className="public-sos-page" aria-labelledby="public-sos-title">
      <header className="public-sos-header">
        <p className="eyebrow">{th ? "ความช่วยเหลือฉุกเฉิน" : "EMERGENCY HELP"}</p>
        <h1 id="public-sos-title">{th ? "ขอความช่วยเหลือ" : "Get help"}</h1>
      </header>

      <section className="public-sos-calm-advice" aria-labelledby="public-sos-advice-title">
        <span className="public-sos-advice-icon" aria-hidden="true">!</span>
        <div>
          <h2 id="public-sos-advice-title">
            {th
              ? "ตั้งสติ และขึ้นไปยังชั้นที่สูงที่สุดที่เข้าถึงได้"
              : "Stay calm and move to the highest accessible floor"}
          </h2>
          <p>
            {th
              ? "หลีกเลี่ยงการเดินผ่านน้ำท่วม อยู่กับสมาชิกในครัวเรือน และปฏิบัติตามคำแนะนำของหน่วยงานทางการ"
              : "Avoid moving through floodwater, stay with household members, and follow official instructions."}
          </p>
        </div>
      </section>

      <section className="public-sos-hold-section" aria-labelledby="public-sos-hold-title">
        <div className="public-sos-hold-heading">
          <h2 id="public-sos-hold-title">
            {actionsVisible
              ? (th ? "เลือกวิธีติดต่อ" : "Choose a contact action")
              : (th ? "กดค้าง 3 วินาที" : "Press and hold for 3 seconds")}
          </h2>
          <p id="public-sos-hold-help">
            {actionsVisible
              ? (th
                ? "การโทรหรือข้อความจะเริ่มเมื่อคุณเลือกปุ่มด้านล่าง"
                : "A call or message starts only after you choose an action below.")
              : (th
                ? "กดค้างจนแถบความคืบหน้าเต็มเพื่อแสดงตัวเลือกการโทรและข้อความ"
                : "Keep holding until the progress bar fills to reveal call and text choices.")}
          </p>
        </div>

        <button
          className={`public-sos-hold-control ${holding ? "holding" : ""} ${actionsVisible ? "complete" : ""}`}
          type="button"
          aria-describedby="public-sos-hold-help"
          aria-pressed={holding}
          disabled={actionsVisible}
          data-hold-state={actionsVisible ? "complete" : holding ? "holding" : "idle"}
          style={holdStyle}
          onPointerDown={handlePointerDown}
          onPointerUp={handlePointerEnd}
          onPointerCancel={handlePointerEnd}
          onLostPointerCapture={cancelHold}
          onKeyDown={handleKeyDown}
          onKeyUp={handleKeyUp}
          onBlur={cancelHold}
        >
          <span className="public-sos-hold-symbol" aria-hidden="true">*</span>
          <strong>
            {actionsVisible
              ? (th ? "พร้อมเลือกการติดต่อ" : "Contact choices available")
              : holding
                ? (th ? "กดค้างต่อไป" : "Keep holding")
                : (th ? "กดค้าง" : "Press and hold")}
          </strong>
          <small>{holdProgress}%</small>
        </button>

        <progress
          className="public-sos-hold-progress"
          value={holdProgress}
          max={100}
          aria-label={th ? "ความคืบหน้าการกดค้าง" : "Press-and-hold progress"}
        >
          {holdProgress}%
        </progress>

        <p className="public-sos-hold-status" role="status" aria-live="polite">
          {actionsVisible
            ? (th
              ? "ตัวเลือกการโทรและข้อความแสดงอยู่ด้านล่าง"
              : "Call and text choices are shown below.")
            : holding
              ? (th ? "กำลังกดค้าง" : "Hold in progress")
              : (th
                ? "ยังไม่มีการโทรหรือส่งข้อความ"
                : "No call or message has been started.")}
        </p>

        {actionsVisible && (
          <div className="public-sos-revealed-actions">
            <a className="public-sos-primary-action" href="tel:1784">
              <span aria-hidden="true">☎</span>
              {th ? "โทรสายด่วน ปภ. 1784" : "Call DDPM 1784"}
            </a>
            <a className="public-sos-secondary-action" href={smsHref}>
              <span aria-hidden="true">▤</span>
              {th ? "เขียน SMS ถึง 1784" : "Compose SMS to 1784"}
            </a>
          </div>
        )}
      </section>

      <section className="public-sos-household" aria-labelledby="public-sos-household-title">
        <div className="public-sos-household-heading">
          <div>
            <p className="eyebrow">{th ? "ข้อมูลจากอุปกรณ์นี้" : "ON-DEVICE DETAILS"}</p>
            <h2 id="public-sos-household-title">
              {th ? "ความต้องการของครัวเรือน" : "Household needs"}
            </h2>
          </div>
          <span>{broadArea}</span>
        </div>

        {selectedNeeds.length > 0 ? (
          <ul className="public-sos-needs-list">
            {selectedNeeds.map((need) => <li key={need.id}>{need[language]}</li>)}
          </ul>
        ) : (
          <p className="public-sos-needs-empty">
            {th
              ? "ไม่มีความต้องการของครัวเรือนที่บันทึกไว้ในอุปกรณ์นี้"
              : "No household needs are recorded on this device."}
          </p>
        )}
      </section>

      <section className="public-sos-hotlines" aria-labelledby="public-sos-hotlines-title">
        <p className="eyebrow">{th ? "โทรฉุกเฉินโดยตรง" : "DIRECT EMERGENCY CALLS"}</p>
        <h2 id="public-sos-hotlines-title">
          {th ? "หมายเลขหน่วยงานทางการ" : "Official hotline numbers"}
        </h2>
        <ul>
          {hotlineActions.map((hotline) => (
            <li key={hotline.number}>
              <a
                href={hotline.href}
                aria-label={`${th ? "โทร" : "Call"} ${hotline.number} · ${th ? hotline.label_th : hotline.label_en}`}
              >
                <strong>{hotline.number}</strong>
                <span>{th ? hotline.label_th : hotline.label_en}</span>
                <b>{th ? "โทร" : "Call"}</b>
              </a>
            </li>
          ))}
        </ul>
      </section>

      <aside className="public-sos-privacy-boundary" aria-labelledby="public-sos-privacy-title">
        <h2 id="public-sos-privacy-title">
          {th ? "ข้อมูลและการติดต่อ" : "Data and contact boundary"}
        </h2>
        <p>
          {th
            ? "หน้านี้จะเปิดแอปโทรศัพท์หรือ SMS เมื่อคุณเลือกเท่านั้น FloodGuard ไม่ติดต่อหน่วยกู้ภัยโดยอัตโนมัติ ข้อความ SMS มีเฉพาะพื้นที่กว้างและความต้องการของครัวเรือนที่แสดงด้านบน โดยไม่มีพิกัดที่แน่นอน"
            : "This page opens your phone or SMS app only when you choose an action. FloodGuard does not contact emergency services automatically. The SMS contains only the broad planning area and household needs shown above, without exact coordinates."}
        </p>
      </aside>
    </section>
  );
}
