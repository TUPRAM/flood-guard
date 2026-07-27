"use client";

import { useId, useMemo, useState } from "react";

import {
  HOUSEHOLD_NEEDS,
  type HouseholdNeedId,
  type HouseholdPlan,
} from "@/lib/household-plan";
import type { Language } from "@/lib/types";

interface PublicShelterPageProps {
  language: Language;
  selectedAreaName: string;
  plan: HouseholdPlan;
  onNavigatePrepare: () => void;
}

type RouteOption = "preferred" | "alternative";
type RouteStepId =
  | "confirm_destination"
  | "confirm_route"
  | "prepare_household"
  | "share_plan";
type ShelterIconName =
  | "accessibility"
  | "arrow"
  | "check"
  | "destination"
  | "phone"
  | "route"
  | "walk"
  | "warning";

const ROUTE_STEPS: Array<{
  id: RouteStepId;
  en: string;
  th: string;
}> = [
  {
    id: "confirm_destination",
    en: "Confirm that the selected destination is open and can receive your household.",
    th: "ยืนยันว่าจุดหมายที่เลือกเปิดให้บริการและสามารถรองรับครัวเรือนของคุณได้",
  },
  {
    id: "confirm_route",
    en: "Confirm the route and travel conditions with DDPM or a local authority.",
    th: "ยืนยันเส้นทางและสภาพการเดินทางกับ ปภ. หรือหน่วยงานท้องถิ่น",
  },
  {
    id: "prepare_household",
    en: "Bring medicine, documents, drinking water, and the support items your household needs.",
    th: "นำยา เอกสาร น้ำดื่ม และอุปกรณ์ช่วยเหลือที่ครัวเรือนของคุณต้องใช้",
  },
  {
    id: "share_plan",
    en: "Tell a trusted contact which destination and route option you selected.",
    th: "แจ้งผู้ติดต่อที่ไว้ใจว่าคุณเลือกจุดหมายและเส้นทางใด",
  },
];

const NEED_SHORT_LABELS: Record<HouseholdNeedId, { en: string; th: string }> = {
  children: { en: "Children", th: "เด็ก" },
  older_adults: { en: "Older adults", th: "ผู้สูงอายุ" },
  mobility_support: { en: "Mobility support", th: "การช่วยเหลือด้านการเคลื่อนไหว" },
  regular_medicine: { en: "Regular medicine", th: "ยาประจำ" },
  pets: { en: "Pets", th: "สัตว์เลี้ยง" },
  limited_transport: { en: "Transport support", th: "การช่วยเหลือด้านการเดินทาง" },
};

function ShelterIcon({ name }: { name: ShelterIconName }) {
  const common = {
    fill: "none",
    stroke: "currentColor",
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    strokeWidth: 1.9,
  };

  return (
    <svg aria-hidden="true" className="public-shelter-icon" viewBox="0 0 24 24">
      {name === "accessibility" && (
        <>
          <circle {...common} cx="12" cy="4.5" r="1.6" />
          <path {...common} d="M10.5 8.2h3.7l2.2 3.4M11.1 8.2l-1 5.1 3.4 2.2 1.7 4M8.9 11.2a5.1 5.1 0 1 0 4.4 8" />
        </>
      )}
      {name === "arrow" && (
        <>
          <path {...common} d="M5 12h14" />
          <path {...common} d="m14 7 5 5-5 5" />
        </>
      )}
      {name === "check" && <path {...common} d="m5 12 4.2 4.2L19 6.5" />}
      {name === "destination" && (
        <>
          <path {...common} d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z" />
          <circle {...common} cx="12" cy="10" r="2.5" />
        </>
      )}
      {name === "phone" && (
        <path {...common} d="M7.1 3.5 10 7.9 8.3 10a15.2 15.2 0 0 0 5.7 5.7l2.1-1.7 4.4 2.9-.8 3a2 2 0 0 1-2 1.5C10.1 20.5 3.5 13.9 2.6 6.3a2 2 0 0 1 1.5-2l3-.8Z" />
      )}
      {name === "route" && (
        <>
          <circle {...common} cx="6" cy="18" r="2" />
          <circle {...common} cx="18" cy="6" r="2" />
          <path {...common} d="M7.8 17.2c2.1-.9 2.5-2.2 1.2-3.8-1.7-2.1-.2-4.3 2.6-4.3h1.1c1.5 0 2.8-.6 3.6-1.7" />
        </>
      )}
      {name === "walk" && (
        <>
          <circle {...common} cx="13" cy="4.2" r="1.7" />
          <path {...common} d="m11.1 8.1 3.1 1.8 2.4 3.3M12 9.2l-1.5 4.2-3.2 2.3M10.5 13.4l3.1 2.3 1.1 4.1M9.7 15.2 8.1 20" />
        </>
      )}
      {name === "warning" && (
        <>
          <path {...common} d="M12 3 2.8 20h18.4L12 3Z" />
          <path {...common} d="M12 9v5M12 17.2h.01" />
        </>
      )}
    </svg>
  );
}

function googleMapsWalkingDirections(destination: string): string {
  const params = new URLSearchParams({
    api: "1",
    destination,
    travelmode: "walking",
  });
  return `https://www.google.com/maps/dir/?${params.toString()}`;
}

export function PublicShelterPage({
  language,
  selectedAreaName,
  plan,
  onNavigatePrepare,
}: PublicShelterPageProps) {
  const th = language === "th";
  const destinationInputId = useId();
  const destinationConfirmationId = useId();
  const routeOptionsId = useId();
  const routeChecklistId = useId();
  const [destinationDraft, setDestinationDraft] = useState("");
  const [selectedDestination, setSelectedDestination] = useState("");
  const [authorityConfirmed, setAuthorityConfirmed] = useState(false);
  const [routeOption, setRouteOption] = useState<RouteOption>("preferred");
  const [completedSteps, setCompletedSteps] = useState<Set<RouteStepId>>(() => new Set());
  const [guidanceSelected, setGuidanceSelected] = useState(false);

  const selectedNeeds = useMemo(
    () => HOUSEHOLD_NEEDS.filter(({ id }) => plan.needs[id]),
    [plan.needs],
  );
  const directionsUrl = selectedDestination
    ? googleMapsWalkingDirections(selectedDestination)
    : "";
  const completedStepCount = completedSteps.size;

  const saveDestination = () => {
    const normalizedDestination = destinationDraft.trim();
    if (!normalizedDestination || !authorityConfirmed) return;
    setSelectedDestination(normalizedDestination);
    setRouteOption("preferred");
    setCompletedSteps(new Set());
    setGuidanceSelected(false);
  };

  const toggleStep = (stepId: RouteStepId) => {
    setCompletedSteps((current) => {
      const next = new Set(current);
      if (next.has(stepId)) next.delete(stepId);
      else next.add(stepId);
      return next;
    });
  };

  return (
    <section className="public-shelter-page" aria-labelledby="public-shelter-title">
      <header className="public-shelter-page__heading">
        <p className="eyebrow">{th ? "การวางแผนไปยังจุดพักพิง" : "Shelter planning"}</p>
        <h1 id="public-shelter-title">{th ? "วางแผนเส้นทางไปยังจุดหมายที่ยืนยันแล้ว" : "Plan a route to a confirmed destination"}</h1>
        <p>
          {th
            ? "กรอกจุดหมายที่คุณยืนยันกับ ปภ. หรือหน่วยงานท้องถิ่น แล้วเปิดเส้นทางเดินใน Google Maps"
            : "Enter a destination you confirmed with DDPM or a local authority, then open walking directions in Google Maps."}
        </p>
      </header>

      <section className="public-shelter-profile" aria-labelledby="public-shelter-profile-title">
        <div className="public-shelter-profile__icon">
          <ShelterIcon name="accessibility" />
        </div>
        <div className="public-shelter-profile__copy">
          <p className="eyebrow">{th ? "ข้อมูลครัวเรือน" : "Household profile"}</p>
          <h2 id="public-shelter-profile-title">
            {selectedNeeds.length > 0
              ? (th ? "ความต้องการที่ควรคำนึงถึงระหว่างเดินทาง" : "Needs to account for while travelling")
              : (th ? "ยังไม่ได้บันทึกความต้องการช่วยเหลือ" : "No support needs recorded")}
          </h2>
          {selectedNeeds.length > 0 && (
            <ul className="public-shelter-profile__needs" aria-label={th ? "ความต้องการของครัวเรือน" : "Household needs"}>
              {selectedNeeds.map(({ id }) => (
                <li key={id}>{NEED_SHORT_LABELS[id][language]}</li>
              ))}
            </ul>
          )}
        </div>
        <button className="public-shelter-profile__edit" type="button" onClick={onNavigatePrepare}>
          {th ? "แก้ไข" : "Edit"}
        </button>
      </section>

      <section className="public-shelter-destination" aria-labelledby="public-shelter-destination-title">
        <div className="public-shelter-section-heading">
          <ShelterIcon name="destination" />
          <div>
            <p className="eyebrow">{th ? "ยืนยันก่อนออกเดินทาง" : "Confirm before travelling"}</p>
            <h2 id="public-shelter-destination-title">{th ? "เลือกจุดหมาย" : "Choose a destination"}</h2>
          </div>
        </div>

        <form
          className="public-shelter-destination__form"
          onSubmit={(event) => {
            event.preventDefault();
            saveDestination();
          }}
        >
          <label htmlFor={destinationInputId}>{th ? "ชื่อหรือที่อยู่ของจุดหมาย" : "Destination name or address"}</label>
          <input
            id={destinationInputId}
            autoComplete="off"
            value={destinationDraft}
            onChange={(event) => {
              setDestinationDraft(event.target.value);
              setAuthorityConfirmed(false);
            }}
            placeholder={th ? "กรอกจุดหมายที่ยืนยันแล้ว" : "Enter the confirmed destination"}
            type="text"
          />
          <label className="public-shelter-destination__confirmation" htmlFor={destinationConfirmationId}>
            <input
              id={destinationConfirmationId}
              checked={authorityConfirmed}
              onChange={(event) => setAuthorityConfirmed(event.target.checked)}
              type="checkbox"
            />
            <span>
              {th
                ? "ฉันได้ยืนยันจุดหมายและเส้นทางกับ ปภ. หรือหน่วยงานท้องถิ่นแล้ว"
                : "I confirmed this destination and route with DDPM or a local authority."}
            </span>
          </label>
          <div className="public-shelter-destination__actions">
            <button
              className="public-shelter-primary-action"
              disabled={!destinationDraft.trim() || !authorityConfirmed}
              type="button"
              onClick={saveDestination}
            >
              {th ? "ใช้จุดหมายนี้" : "Use this destination"}
            </button>
            <a className="public-shelter-call-action" href="tel:1784">
              <ShelterIcon name="phone" />
              <span>{th ? "โทร 1784 เพื่อยืนยัน" : "Call 1784 to confirm"}</span>
            </a>
          </div>
        </form>
      </section>

      <section className="public-shelter-route-overview" aria-labelledby="public-shelter-route-title">
        <div
          className="public-shelter-route-overview__graphic"
          role="img"
          aria-label={th
            ? `ภาพรวมเส้นทางจาก ${selectedAreaName || "พื้นที่วางแผนที่เลือก"} ไปยัง ${selectedDestination || "จุดหมายที่ยังไม่ได้เลือก"}`
            : `Route overview from ${selectedAreaName || "the selected planning area"} to ${selectedDestination || "a destination yet to be selected"}`}
        >
          <span className="public-shelter-route-overview__start" aria-hidden="true">
            <ShelterIcon name="walk" />
          </span>
          <span className="public-shelter-route-overview__line" aria-hidden="true" />
          <span className="public-shelter-route-overview__destination" aria-hidden="true">
            <ShelterIcon name="destination" />
          </span>
        </div>

        <div className="public-shelter-route-overview__summary">
          <p className="eyebrow">{th ? "จุดหมายที่เลือก" : "Selected destination"}</p>
          <h2 id="public-shelter-route-title">
            {selectedDestination || (th ? "กรอกและยืนยันจุดหมายด้านบน" : "Enter and confirm a destination above")}
          </h2>
          <dl>
            <div>
              <dt>{th ? "พื้นที่วางแผน" : "Planning area"}</dt>
              <dd>{selectedAreaName || (th ? "ไม่ได้เลือกพื้นที่" : "No area selected")}</dd>
            </div>
            <div>
              <dt>{th ? "รูปแบบการเดินทาง" : "Travel mode"}</dt>
              <dd>{th ? "เดินเท้า" : "Walking"}</dd>
            </div>
            <div>
              <dt>{th ? "ตัวเลือกเส้นทาง" : "Route option"}</dt>
              <dd>{routeOption === "preferred"
                ? (th ? "ตัวเลือกเส้นทางที่ต้องการ" : "Preferred route option")
                : (th ? "ตัวเลือกเส้นทางอื่น" : "Alternative route option")}</dd>
            </div>
          </dl>
        </div>
      </section>

      <fieldset className="public-shelter-route-options" aria-describedby={routeOptionsId}>
        <legend>{th ? "ตัวเลือกเส้นทาง" : "Route options"}</legend>
        <p id={routeOptionsId}>
          {th
            ? "Google Maps จะแสดงเส้นทางเดินที่มีให้ตรวจสอบ คุณเป็นผู้เลือกเส้นทางหลังจากตรวจสอบเงื่อนไขการเดินทาง"
            : "Google Maps will show walking routes for review. Choose a route after confirming travel conditions."}
        </p>
        <label className={routeOption === "preferred" ? "selected" : ""}>
          <input
            checked={routeOption === "preferred"}
            name="public-shelter-route-option"
            onChange={() => setRouteOption("preferred")}
            type="radio"
            value="preferred"
          />
          <span>
            <b>{th ? "ตัวเลือกเส้นทางที่ต้องการ" : "Preferred route option"}</b>
            <small>{th ? "เปิดเส้นทางเดินไปยังจุดหมายที่เลือก" : "Open walking directions to the selected destination"}</small>
          </span>
          <ShelterIcon name="route" />
        </label>
        <label className={routeOption === "alternative" ? "selected" : ""}>
          <input
            checked={routeOption === "alternative"}
            name="public-shelter-route-option"
            onChange={() => setRouteOption("alternative")}
            type="radio"
            value="alternative"
          />
          <span>
            <b>{th ? "ตัวเลือกเส้นทางอื่น" : "Alternative route option"}</b>
            <small>{th ? "ตรวจสอบและเลือกเส้นทางเดินอื่นใน Google Maps" : "Review and choose another walking route in Google Maps"}</small>
          </span>
          <ShelterIcon name="arrow" />
        </label>
      </fieldset>

      <section className="public-shelter-checklist" aria-labelledby={routeChecklistId}>
        <div className="public-shelter-checklist__heading">
          <div>
            <p className="eyebrow">{th ? "ก่อนเริ่มคำแนะนำ" : "Before starting guidance"}</p>
            <h2 id={routeChecklistId}>{th ? "รายการตรวจสอบทีละขั้น" : "Step-by-step checklist"}</h2>
          </div>
          <span aria-label={th ? `ทำแล้ว ${completedStepCount} จาก ${ROUTE_STEPS.length} ขั้น` : `${completedStepCount} of ${ROUTE_STEPS.length} steps complete`}>
            {completedStepCount}/{ROUTE_STEPS.length}
          </span>
        </div>
        <progress max={ROUTE_STEPS.length} value={completedStepCount}>
          {completedStepCount}/{ROUTE_STEPS.length}
        </progress>
        <ol>
          {ROUTE_STEPS.map((step, index) => (
            <li className={completedSteps.has(step.id) ? "completed" : ""} key={step.id}>
              <label>
                <input
                  checked={completedSteps.has(step.id)}
                  onChange={() => toggleStep(step.id)}
                  type="checkbox"
                />
                <span className="public-shelter-checklist__number" aria-hidden="true">
                  {completedSteps.has(step.id) ? <ShelterIcon name="check" /> : index + 1}
                </span>
                <span>{step[language]}</span>
              </label>
            </li>
          ))}
        </ol>
      </section>

      <aside className="public-shelter-safety" aria-labelledby="public-shelter-safety-title">
        <ShelterIcon name="warning" />
        <div>
          <h2 id="public-shelter-safety-title">{th ? "ข้อควรระวังด้านความปลอดภัย" : "Safety disclaimer"}</h2>
          <p>
            {th
              ? "คำแนะนำนี้ช่วยเปิดเส้นทางเท่านั้น โปรดยืนยันว่าจุดหมายเปิดให้บริการ ตรวจสอบสภาพเส้นทางในเวลาที่เดินทาง และปฏิบัติตามคำแนะนำของ ปภ. และหน่วยงานท้องถิ่น ห้ามเดินหรือขับรถลงในน้ำท่วมที่ไหลเชี่ยวหรือลึก"
              : "This guidance only opens directions. Confirm that the destination is open, check route conditions at the time of travel, and follow DDPM and local-authority instructions. Do not walk or drive into moving or deep floodwater."}
          </p>
        </div>
      </aside>

      <div className="public-shelter-guidance">
        {selectedDestination ? (
          <a
            className="public-shelter-guidance__start"
            href={directionsUrl}
            onClick={() => setGuidanceSelected(true)}
            rel="noopener noreferrer"
            target="_blank"
          >
            <ShelterIcon name="walk" />
            <span>{th ? "เริ่มคำแนะนำ" : "Start Guidance"}</span>
          </a>
        ) : (
          <button className="public-shelter-guidance__start" disabled type="button">
            <ShelterIcon name="walk" />
            <span>{th ? "เริ่มคำแนะนำ" : "Start Guidance"}</span>
          </button>
        )}
        <p>
          {th
            ? "เปิด Google Maps ในโหมดเดินเท้า โดย FloodGuard ไม่เก็บจุดเริ่มต้นหรือตำแหน่งที่แน่นอนของคุณ"
            : "Opens Google Maps in walking mode. FloodGuard does not collect your origin or exact location."}
        </p>
        <p aria-live="polite" className="public-shelter-guidance__status" role="status">
          {guidanceSelected && selectedDestination
            ? (th
              ? `เลือกคำแนะนำการเดินไปยัง ${selectedDestination} แล้ว โปรดตรวจสอบเส้นทางใน Google Maps ก่อนเดินทาง`
              : `Walking guidance selected for ${selectedDestination}. Review the route in Google Maps before travelling.`)
            : ""}
        </p>
      </div>
    </section>
  );
}
