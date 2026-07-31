import type { PublicPreparednessArea } from "@floodguard/contracts";

import type { Language } from "./types";

export type PublicHazardSignalCode =
  | "elevated_planning_priority"
  | "life_safety_exposure"
  | "critical_route_access"
  | "essential_service_access";

export interface PublicHazardSignal {
  code: PublicHazardSignalCode;
  label_en: string;
  label_th: string;
}

const SIGNAL_LABELS: Record<PublicHazardSignalCode, { en: string; th: string }> = {
  elevated_planning_priority: {
    en: "Elevated planning priority for this area",
    th: "พื้นที่นี้มีลำดับความสำคัญในการวางแผนสูง",
  },
  life_safety_exposure: {
    en: "Life-safety needs flagged for local checks",
    th: "มีความต้องการด้านความปลอดภัยของชีวิตที่ต้องตรวจสอบในพื้นที่",
  },
  critical_route_access: {
    en: "Important route access needs confirmation",
    th: "การเข้าถึงเส้นทางสำคัญต้องได้รับการยืนยัน",
  },
  essential_service_access: {
    en: "Essential service access needs confirmation",
    th: "การเข้าถึงบริการจำเป็นต้องได้รับการยืนยัน",
  },
};

/**
 * Derives preparedness signals from the area record already shown on Home.
 *
 * Signals describe planning exposure carried by the area's own priority and
 * recommendation code. They come from historical flood evidence, never assert
 * current water levels, and deliberately exclude evidence-quality caveats
 * (freshness, sufficiency) — those stay in the hazard panel so a data caveat
 * is never presented to the public as a hazard.
 */
export function derivePublicHazardSignals(
  area: PublicPreparednessArea | undefined,
): PublicHazardSignal[] {
  if (!area) return [];

  const codes: PublicHazardSignalCode[] = [];

  if (area.planning_priority_0_100 >= 50) {
    codes.push("elevated_planning_priority");
  }

  if (
    area.recommendation_code === "life_safety_exposure"
    || area.recommendation_code === "critical_route_access"
    || area.recommendation_code === "essential_service_access"
  ) {
    codes.push(area.recommendation_code);
  }

  return codes.map((code) => ({
    code,
    label_en: SIGNAL_LABELS[code].en,
    label_th: SIGNAL_LABELS[code].th,
  }));
}

export function hazardSignalLabel(
  signal: PublicHazardSignal,
  language: Language,
): string {
  return language === "th" ? signal.label_th : signal.label_en;
}

export function hazardSignalSummary(count: number, language: Language): string {
  if (language === "th") {
    return `พบสัญญาณการเตรียมพร้อม ${count} รายการในพื้นที่ของคุณ`;
  }
  return count === 1
    ? "1 preparedness signal for your area"
    : `${count} preparedness signals for your area`;
}
