/**
 * The practice scenarios of the Public home map: seven moments of the September 2024 Mae Sai replay, each seen from
 * one of two example homes in Mae Sai town. This file holds only the list, the names and the colour tone of each
 * state, so the header can show the menu without loading the replay.
 *
 * Every scenario is named after the state it is meant to show. The state itself is computed from the replay data in
 * `public-practice.ts`; a unit test reads the published replay files and fails when a scenario no longer computes to
 * its own name.
 */

import type { Language } from "./types";

type Localized = Record<Language, string>;

/** What the replay says about one home at one hour, from calm to water at the home. */
export type PracticeState =
  | "normal"
  | "heads_up"
  | "roads_cut"
  | "reach_at_risk"
  | "cut_off"
  | "water_at_home"
  | "going_down";

/** The example home a scenario looks from: one that stays dry and is cut off, and a neighbour that floods. */
export type PracticeHomeId = "dry" | "flooded";

export interface PracticeHome {
  latitude: number;
  longitude: number;
  /** Subdistrict of the point (HDX COD-AB code). */
  tambonId: string;
}

/**
 * Two points of the replay's resident grid in Mae Sai town, about 110 m apart. They are points of the model with
 * residents nearby (WorldPop 2020 at road nodes), not addresses.
 */
export const PRACTICE_HOMES: Readonly<Record<PracticeHomeId, PracticeHome>> = {
  dry: { latitude: 20.44042, longitude: 99.88718, tambonId: "TH570901" },
  flooded: { latitude: 20.44126, longitude: 99.88662, tambonId: "TH570901" },
};

export interface PracticeScenario {
  /** The state this scenario shows; also its id. */
  id: PracticeState;
  home: PracticeHomeId;
  /** Whole hours since 9 Sep 2024 00:00 ICT on the replay clock. */
  hour: number;
}

/** In the order of the menu: the flood as it rose, the two outcomes at the peak, then the recession. */
export const PRACTICE_SCENARIOS: readonly PracticeScenario[] = [
  { id: "normal", home: "dry", hour: 12 },
  { id: "heads_up", home: "dry", hour: 40 },
  { id: "roads_cut", home: "dry", hour: 46 },
  { id: "reach_at_risk", home: "dry", hour: 48 },
  { id: "cut_off", home: "dry", hour: 84 },
  { id: "water_at_home", home: "flooded", hour: 84 },
  { id: "going_down", home: "dry", hour: 132 },
];

export function practiceScenario(id: PracticeState | null | undefined): PracticeScenario | undefined {
  return PRACTICE_SCENARIOS.find((scenario) => scenario.id === id);
}

/** Name of a scenario in the menu. */
export const PRACTICE_SCENARIO_LABELS: Readonly<Record<PracticeState, Localized>> = {
  normal: { en: "Normal day", th: "วันปกติ" },
  heads_up: { en: "Shallow water on roads", th: "น้ำตื้นบนถนน" },
  roads_cut: { en: "Roads under water", th: "ถนนจมน้ำ" },
  reach_at_risk: { en: "Walk to a shelter nearly cut", th: "ทางเดินไปที่พักพิงใกล้ถูกตัด" },
  cut_off: { en: "Cut off, home dry", th: "ถูกตัดขาด บ้านยังแห้ง" },
  water_at_home: { en: "Water at home", th: "น้ำถึงบ้าน" },
  going_down: { en: "Water going down", th: "น้ำกำลังลด" },
};

/**
 * Colour tone of the banner and of Hazard Info. "neutral" is the grey of a day without practice: the app has no
 * feed of current water, so it never shows the green of "calm" on its own.
 */
export type PracticeTone = "neutral" | "calm" | "watch" | "alert" | "danger" | "easing";

export const PRACTICE_STATE_TONE: Readonly<Record<PracticeState, PracticeTone>> = {
  normal: "calm",
  heads_up: "watch",
  roads_cut: "alert",
  reach_at_risk: "alert",
  cut_off: "danger",
  water_at_home: "danger",
  going_down: "easing",
};

export const PRACTICE_MENU_COPY = {
  button: { en: "Practice scenarios", th: "สถานการณ์ฝึกซ้อม" },
  heading: { en: "Practice: replay of September 2024", th: "ฝึกซ้อม: ภาพจำลองเดือนกันยายน 2567 (2024)" },
  off: { en: "Today (no practice)", th: "วันนี้ (ไม่ฝึกซ้อม)" },
  /** The place the header names while a scenario is shown. */
  homePlace: { en: "Example home · Mae Sai", th: "บ้านตัวอย่าง · แม่สาย" },
  loading: { en: "Loading the practice replay…", th: "กำลังโหลดภาพจำลองเพื่อฝึกซ้อม…" },
  unavailable: { en: "Practice replay unavailable", th: "ภาพจำลองเพื่อฝึกซ้อมไม่พร้อมใช้งาน" },
  unavailableDetail: {
    en: "The replay files could not be loaded. Check the connection and choose the scenario again.",
    th: "โหลดไฟล์ภาพจำลองไม่สำเร็จ โปรดตรวจการเชื่อมต่อแล้วเลือกสถานการณ์อีกครั้ง",
  },
} as const satisfies Record<string, Localized>;
