/**
 * What the first screen of the Public Shelter page says: the banner under the destination field and the note at the
 * foot of the map. Pure functions; no DOM access.
 *
 * The page knows no shelter that is open today, so its banner never turns green. It is grey with no destination,
 * amber while the destination in the field has not been confirmed with an authority, and blue once the reader says
 * it has been, with the distance the page could work out.
 */

import type { PracticeTone } from "./public-practice-scenarios";
import { formatRouteDistance } from "./public-route";
import type { ShelterHistorySite } from "./public-shelter-history";
import type { Language } from "./types";

type Localized = Record<Language, string>;

export const SHELTER_PAGE_COPY = {
  title: { en: "Check a destination and travel options", th: "ตรวจสอบจุดหมายและการเดินทาง" },
  fieldLabel: { en: "Destination name or address", th: "ชื่อหรือที่อยู่ของจุดหมาย" },
  fieldNext: { en: "Next", th: "ถัดไป" },
  bannerNone: { en: "No destination chosen yet", th: "ยังไม่ได้เลือกจุดหมาย" },
  bannerUnconfirmed: { en: "Not confirmed yet", th: "ยังไม่ได้ยืนยัน" },
  bannerSet: { en: "Destination set", th: "เลือกจุดหมายแล้ว" },
  /** The line of the note that is always there: what the page does not know. */
  noteUnknown: {
    en: "This app does not know which place is open today · confirm with DDPM 1784",
    th: "แอปนี้ไม่ทราบว่าสถานที่ใดเปิดรับในวันนี้ · โปรดยืนยันกับ ปภ. 1784",
  },
  routeWalk: { en: "Road-following walk · verify conditions", th: "เส้นทางเดินตามถนน · ตรวจสอบสภาพจริง" },
  routeDirect: { en: "Straight line for orientation only · not a walking route", th: "เส้นตรงเพื่อดูทิศทางเท่านั้น · ไม่ใช่เส้นทางเดิน" },
  from: { en: "From", th: "จาก" },
  panelEyebrow: { en: "SHELTER AND TRAVEL", th: "ที่พักพิงและการเดินทาง" },
  panelHeading: { en: "Choose a destination", th: "เลือกจุดหมาย" },
  panelClose: { en: "Close shelter and travel details", th: "ปิดรายละเอียดที่พักพิงและการเดินทาง" },
  unknown: {
    en: "Start with a destination you checked with an authority. This app does not know its current capacity or operating status.",
    th: "เริ่มจากจุดหมายที่คุณตรวจสอบกับหน่วยงานแล้ว ความจุและการเปิดใช้จริงยังไม่ทราบจากแอปนี้",
  },
  empty: {
    en: "Type the name or address of the place you will go to in the field above the map.",
    th: "พิมพ์ชื่อหรือที่อยู่ของสถานที่ที่คุณจะไปในช่องเหนือแผนที่",
  },
  emptyWithHistory: {
    en: "Type the name or address of the place you will go to in the field above the map, or take one of the places listed below.",
    th: "พิมพ์ชื่อหรือที่อยู่ของสถานที่ที่คุณจะไปในช่องเหนือแผนที่ หรือเลือกจากสถานที่ในรายการด้านล่าง",
  },
  confirmation: {
    en: "I confirmed this destination and route with DDPM or a local authority.",
    th: "ฉันได้ยืนยันจุดหมายและเส้นทางกับ ปภ. หรือหน่วยงานท้องถิ่นแล้ว",
  },
  use: { en: "Use this destination", th: "ใช้จุดหมายนี้" },
  call: { en: "Call DDPM 1784 to confirm", th: "โทร ปภ. 1784 เพื่อยืนยัน" },
  safetyHeading: { en: "Safety disclaimer", th: "ข้อควรระวังด้านความปลอดภัย" },
  safety: {
    en: "This app does not know whether the destination is open, its capacity, or which roads are flooded now. A walking route, when available, comes from road-map data; otherwise only straight-line orientation is shown. Confirm conditions with DDPM or local authorities. Do not walk or drive into moving or deep floodwater.",
    th: "แอปนี้ไม่ทราบว่าสถานที่เปิดอยู่ มีความจุเท่าใด หรือถนนสายใดถูกน้ำท่วมในขณะนี้ หากแสดงเส้นทางเดิน จะคำนวณจากแผนที่ถนนเท่านั้น หากไม่มีเส้นทาง จะแสดงเพียงทิศทางและระยะเส้นตรง โปรดยืนยันข้อมูลกับ ปภ. หรือหน่วยงานท้องถิ่น ห้ามเดินหรือขับรถลงในน้ำท่วมที่ไหลเชี่ยวหรือลึก",
  },
} as const satisfies Record<string, Localized>;

/** The steps of the page's checklist. */
export type ShelterStepId = "confirm_destination" | "confirm_route" | "prepare_household" | "share_plan";

/**
 * What the reader has entered on the Shelter page. The Public shell keeps it for the visit, so it is still there
 * when the reader comes back from another page (the sheet itself sends them to Prepare to edit the household).
 * Nothing of it is saved on the device.
 */
export interface ShelterTrip {
  /** What stands in the destination field. */
  draft: string;
  /** The place of 2024 the field was filled from; null for a typed destination. */
  draftSite: ShelterHistorySite | null;
  /** The destination in use: the reader said an authority confirmed it. Empty until then. */
  destination: string;
  destinationSite: ShelterHistorySite | null;
  authorityConfirmed: boolean;
  completedSteps: ShelterStepId[];
}

export const EMPTY_SHELTER_TRIP: ShelterTrip = {
  draft: "",
  draftSite: null,
  destination: "",
  destinationSite: null,
  authorityConfirmed: false,
  completedSteps: [],
};

export interface ShelterBannerInput {
  /** What stands in the destination field. */
  draft: string;
  /** The destination in use: the reader said an authority confirmed it. Empty until then. */
  destination: string;
  /**
   * The practice scenario shown, with the sentence the replay gives this page: whether the example home still has a
   * walk to a shelter reported in 2024. It is the banner while no destination is in the field.
   */
  practice?: { tone: PracticeTone; text: string };
  /** The walking route from the road map, when the router answered. */
  walk?: { metres: number; minutes: number };
  /** The straight-line distance, when both ends are known. */
  directMetres?: number;
}

export interface ShelterBanner {
  tone: PracticeTone;
  icon: "shelter" | "hazard" | "route";
  text: string;
}

/**
 * The tone of a practice scenario as this page shows it. The scenario without water is green on the Home map; here
 * it is grey, because a green line on the Shelter page would read as "a shelter is open".
 */
export function shelterTone(tone: PracticeTone): PracticeTone {
  return tone === "calm" ? "neutral" : tone;
}

/** The banner of the page for what the reader has entered so far. The figures come first: a long name is cut last. */
export function shelterBanner(input: ShelterBannerInput, language: Language): ShelterBanner {
  const th = language === "th";
  const name = input.destination || input.draft.trim();
  if (!name) {
    if (!input.practice) return { tone: "neutral", icon: "shelter", text: SHELTER_PAGE_COPY.bannerNone[language] };
    return { tone: shelterTone(input.practice.tone), icon: "shelter", text: input.practice.text };
  }
  if (!input.destination) return { tone: "watch", icon: "hazard", text: `${SHELTER_PAGE_COPY.bannerUnconfirmed[language]}: ${name}` };
  if (input.walk) {
    const distance = formatRouteDistance(input.walk.metres, language);
    return {
      tone: "easing",
      icon: "route",
      text: th
        ? `เส้นทางเดิน ${distance} · ประมาณ ${input.walk.minutes} นาที · ${name}`
        : `Walking route ${distance} · about ${input.walk.minutes} min · ${name}`,
    };
  }
  if (input.directMetres !== undefined) {
    const distance = formatRouteDistance(input.directMetres, language);
    return {
      tone: "easing",
      icon: "route",
      text: th ? `เส้นตรง ${distance} · ไม่ใช่เส้นทางเดิน · ${name}` : `Straight line ${distance} · not a walking route · ${name}`,
    };
  }
  return { tone: "easing", icon: "route", text: `${SHELTER_PAGE_COPY.bannerSet[language]}: ${name}` };
}
