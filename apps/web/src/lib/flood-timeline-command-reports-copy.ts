/**
 * Wording of the reports on the map and of "Known by now" on the Command exercise replay (Mae Sai, September 2024),
 * in English and Thai: the markers and their popups, the exercise items, the sign of the reports saved on this
 * device, the rows of the list, the two modes and the notices.
 *
 * Three kinds of thing are named apart everywhere: place records are what news reported in 2024 (not surveyed);
 * exercise items are invented for practice and say so on their first line; reports saved on this device carry the
 * date they were saved and are outside the replay clock. Nothing here calls an item checked or proven, and the page
 * is not real-time and not an official warning. Each string is scanned by the shared wording lint.
 *
 * Thai: written by an AI assistant in the plain register of Thai public disaster notices; no native speaker has
 * reviewed it (owner decision, 5 Oct 2026), and the information drawer says so.
 */

import { formatDateWithYear, formatHourStamp, formatLocalStamp, formatShortDate, TIMELINE_EPOCH_MS, type Language, type Localized, type ReportedDepths } from "./flood-timeline";
import { COMMAND_LAST_HOUR, roundModelFigure } from "./flood-timeline-command";
import type { CommandFeedItem, CommandMode, PlaceRecordTally } from "./flood-timeline-command-feed";
import type {
  ExerciseDepthBand,
  ExerciseHandling,
  ExerciseItem,
  ExerciseNeed,
  ExercisePeopleBand,
  ExerciseStatus,
  ExerciseUrgency,
} from "./flood-timeline-command-incidents";
import { reportedDepthText } from "./flood-timeline-reported-depths";

const pick = (text: Localized, language: Language): string => (language === "th" ? text.th : text.en);

// --- Exercise items --------------------------------------------------------------------------------------

export const COMMAND_EXERCISE = {
  /** The lane tag on the first line of every invented item. */
  tag: { en: "Exercise · invented", th: "ฝึกซ้อม · สมมุติขึ้น" },
  /** The short tag on a marker's line and beside the count of open items. */
  short: { en: "EX", th: "EX" },
  call: { en: "Call for help", th: "ขอความช่วยเหลือ" },
  reportDepth: { en: "Depth report", th: "รายงานระดับน้ำ" },
  reportRoad: { en: "Road report", th: "รายงานสภาพถนน" },
  assign: { en: "Assign", th: "มอบหมาย" },
  details: { en: "Details", th: "รายละเอียด" },
  said: { en: "What the item says", th: "ข้อความของรายการ" },
  where: { en: "Where", th: "สถานที่" },
  what: { en: "What", th: "สถานการณ์" },
  when: { en: "When", th: "เวลา" },
  modelHere: { en: "Model here", th: "แบบจำลอง ณ จุดนี้" },
  handling: { en: "Handling", th: "การดำเนินการ" },
  needs: { en: "needs", th: "ต้องการ" },
  noNeeds: { en: "no need stated", th: "ไม่ระบุความต้องการ" },
  currentNotModelled: { en: "current not modelled", th: "ไม่ได้จำลองกระแสน้ำ" },
  ruleTitle: { en: "How urgency is set", th: "การกำหนดระดับความเร่งด่วน" },
  notReal: {
    en: "Invented for practice. No real person, call or address. Never counted with real reports.",
    th: "สมมุติขึ้นเพื่อการฝึกซ้อม ไม่ใช่บุคคล การขอความช่วยเหลือ หรือที่อยู่จริง และไม่นับรวมกับรายงานจริง",
  },
  itemsOff: { en: "Exercise items are switched off", th: "ปิดการแสดงรายการฝึกซ้อมไว้" },
  openCaption: { en: "open items", th: "ยังไม่ปิด" },
  select: { en: "Select for the item", th: "เลือกเพื่อดูรายการ" },
} as const satisfies Record<string, Localized>;

export const COMMAND_URGENCY: Readonly<Record<ExerciseUrgency, Localized>> = {
  life_at_risk: { en: "Life at risk", th: "เสี่ยงต่อชีวิต" },
  urgent: { en: "Urgent", th: "เร่งด่วน" },
  information: { en: "Information", th: "ข้อมูลทั่วไป" },
};

export const COMMAND_STATUS: Readonly<Record<ExerciseStatus, Localized>> = {
  new: { en: "new", th: "ใหม่" },
  acknowledged: { en: "acknowledged", th: "รับทราบแล้ว" },
  assigned: { en: "assigned", th: "มอบหมายแล้ว" },
  done: { en: "done", th: "เสร็จสิ้น" },
  dropped: { en: "dropped", th: "ยุติ" },
};

export const COMMAND_DEPTH_BAND: Readonly<Record<ExerciseDepthBand, Localized>> = {
  not_stated: { en: "depth not stated", th: "ไม่ระบุระดับน้ำ" },
  ankle: { en: "ankle-deep water", th: "น้ำระดับข้อเท้า" },
  knee: { en: "knee-deep water", th: "น้ำระดับเข่า" },
  waist: { en: "waist-deep water", th: "น้ำระดับเอว" },
  chest: { en: "chest-deep water", th: "น้ำระดับอก" },
  over_head: { en: "water above head height", th: "น้ำสูงเกินศีรษะ" },
};

export const COMMAND_PEOPLE_BAND: Readonly<Record<ExercisePeopleBand, Localized>> = {
  none_stated: { en: "no people stated", th: "ไม่ระบุจำนวนคน" },
  "1-2": { en: "1–2 people", th: "1–2 คน" },
  "3-5": { en: "3–5 people", th: "3–5 คน" },
  "6-10": { en: "6–10 people", th: "6–10 คน" },
  "11-20": { en: "11–20 people", th: "11–20 คน" },
  over_20: { en: "more than 20 people", th: "มากกว่า 20 คน" },
};

export const COMMAND_NEED: Readonly<Record<ExerciseNeed, Localized>> = {
  evacuation: { en: "evacuation", th: "การอพยพ" },
  medical: { en: "medical help", th: "การรักษาพยาบาล" },
  food_water: { en: "food and drinking water", th: "อาหารและน้ำดื่ม" },
  information: { en: "information", th: "ข้อมูล" },
  power: { en: "an electrical check", th: "การตรวจระบบไฟฟ้า" },
  road_clearing: { en: "road clearing", th: "การเปิดเส้นทาง" },
};

/** "Call for help", "Depth report" or "Road report". */
export function commandItemKind(item: Pick<ExerciseItem, "kind" | "subject">, language: Language): string {
  return pick(item.kind === "call" ? COMMAND_EXERCISE.call : item.subject === "road" ? COMMAND_EXERCISE.reportRoad : COMMAND_EXERCISE.reportDepth, language);
}

/** Line 1 of a popup: "Exercise · invented · Call for help · EX-05". The tag comes first and is never dropped. */
export function commandItemTitle(item: Pick<ExerciseItem, "id" | "kind" | "subject">, language: Language): string {
  return `${pick(COMMAND_EXERCISE.tag, language)} · ${commandItemKind(item, language)} · ${item.id}`;
}

/** "placed to within ±150 m" / "ตำแหน่งคลาดเคลื่อนได้ ±150 ม.". */
export function commandItemTolerance(metres: number, language: Language): string {
  return language === "th" ? `ตำแหน่งคลาดเคลื่อนได้ ±${metres} ม.` : `placed to within ±${metres} m`;
}

/** Line 2: the place (Thai first), its subdistrict and how closely it is placed. */
export function commandItemPlaceLine(item: Pick<ExerciseItem, "place" | "toleranceM">, tambon: Localized | null, language: Language): string {
  const names = language === "th" ? item.place.th : `${item.place.th} (${item.place.en})`;
  const area = tambon ? (language === "th" ? ` · ต.${tambon.th}` : ` · ${tambon.en} subdistrict`) : "";
  return `${names}${area} · ${commandItemTolerance(item.toleranceM, language)}`;
}

/** Line 3: the depth band, the number of people and the needs. */
export function commandItemWhatLine(item: Pick<ExerciseItem, "depthBand" | "peopleBand" | "needs">, language: Language): string {
  const needs = item.needs.length > 0
    ? `${pick(COMMAND_EXERCISE.needs, language)}: ${item.needs.map((need) => pick(COMMAND_NEED[need], language)).join(language === "th" ? " " : ", ")}`
    : pick(COMMAND_EXERCISE.noNeeds, language);
  return [pick(COMMAND_DEPTH_BAND[item.depthBand], language), pick(COMMAND_PEOPLE_BAND[item.peopleBand], language), needs].join(" · ");
}

/** "6 h" / "6 ชม.": the waiting clock under a marker. Replay hours, never hours of today. */
export function commandWaitingShort(hours: number, language: Language): string {
  return language === "th" ? `${hours} ชม.` : `${hours} h`;
}

/**
 * The line under an exercise marker on the map: the short exercise tag first, which is never dropped (a marker says
 * "invented" wherever it is shown, also on a cropped photo of the map), then the callsign once a team is assigned and
 * the hours an urgent or life-at-risk item has waited.
 */
export function commandItemLine(
  shows: { showsCallsign: boolean; showsWaiting: boolean },
  handling: Pick<ExerciseHandling, "callsign">,
  waiting: number,
  language: Language,
): { tag: string; text: string } {
  const parts = [
    shows.showsCallsign && handling.callsign ? handling.callsign : "",
    shows.showsWaiting && waiting > 0 ? commandWaitingShort(waiting, language) : "",
  ].filter(Boolean);
  return { tag: pick(COMMAND_EXERCISE.short, language), text: parts.join(" · ") };
}

/** "waiting 6 h in replay time" / "รอมาแล้ว 6 ชม. ตามเวลาในการย้อนดู". */
export function commandWaitingText(hours: number, language: Language): string {
  if (hours <= 0) return language === "th" ? "เพิ่งได้รับในชั่วโมงนี้ของการย้อนดู" : "received at this replay hour";
  return language === "th" ? `รอมาแล้ว ${hours} ชม. ตามเวลาในการย้อนดู` : `waiting ${hours} h in replay time`;
}

/** Line 4: when the item was received on the replay clock, and how long it has waited while it is open. */
export function commandItemWhenLine(item: Pick<ExerciseItem, "hour">, waiting: number | null, language: Language): string {
  const received = language === "th" ? `ได้รับเมื่อ ${formatHourStamp(item.hour, language)} (เวลาในการย้อนดู)` : `Received ${formatHourStamp(item.hour, language)} ICT (replay time)`;
  return waiting === null ? received : `${received} · ${commandWaitingText(waiting, language)}`;
}

/**
 * Line 5: what the model has at the point at this replay hour, always with "current not modelled". `depth` is the
 * modelled depth in metres, 0 where the model is dry, null outside the terrain grid and undefined while the water
 * layer has not loaded.
 */
export function commandModelHereLine(depth: number | null | undefined, language: Language): string {
  const th = language === "th";
  const lead = pick(COMMAND_EXERCISE.modelHere, language);
  const current = pick(COMMAND_EXERCISE.currentNotModelled, language);
  if (depth === undefined) return `${lead}: ${th ? "ยังโหลดชั้นข้อมูลน้ำไม่เสร็จ" : "the water layer has not loaded"}`;
  if (depth === null) return `${lead}: ${th ? "อยู่นอกพื้นที่ที่แบบจำลองครอบคลุม" : "outside the modelled area"}`;
  if (!(depth > 0)) return `${lead}: ${th ? "แห้ง ณ ชั่วโมงนี้ของการย้อนดู" : "dry at this replay hour"} · ${current}`;
  const value = depth < 0.05 ? "<0.1" : `~${depth.toFixed(1)}`;
  return `${lead}: ${th ? `น้ำลึก ${value} ม. ณ ชั่วโมงนี้ของการย้อนดู` : `${value} m of water at this replay hour`} · ${current}`;
}

/** Line 6: the urgency in words and the handling state, with the callsign once a team is assigned. */
export function commandItemStateLine(item: Pick<ExerciseItem, "urgency">, handling: ExerciseHandling, language: Language): string {
  const state = pick(COMMAND_STATUS[handling.status], language);
  const callsign = handling.status === "assigned" && handling.callsign ? ` · ${handling.callsign}` : "";
  return `${pick(COMMAND_URGENCY[item.urgency], language)} · ${state}${callsign}`;
}

/** What a marker says to a screen reader, and on hover: the tag first, then the kind, the urgency, the state and the place. */
export function commandItemMarkerTitle(item: Pick<ExerciseItem, "id" | "kind" | "subject" | "urgency" | "place">, handling: ExerciseHandling, language: Language): string {
  return `${commandItemTitle(item, language)}: ${commandItemStateLine(item, handling, language)} · ${pick(item.place, language)}`;
}

/** Under the count of open items, beside the "!!" glyph: "2 at risk" / "เสี่ยงต่อชีวิต 2". Thai puts the words first. */
export function commandAtRiskShort(count: number, language: Language): string {
  return language === "th" ? `เสี่ยงต่อชีวิต ${count}` : `${count} at risk`;
}

/** Figure 4 of the situation card, for a screen reader: "Open exercise items: 3 (invented). 1 at life at risk." */
export function commandOpenItemsText(open: number, lifeAtRisk: number, language: Language): string {
  if (language === "th") return `รายการฝึกซ้อมที่ยังไม่ปิด ${open} รายการ (สมมุติขึ้น)${lifeAtRisk > 0 ? ` เสี่ยงต่อชีวิต ${lifeAtRisk} รายการ` : ""}`;
  return `Open exercise items: ${open} (invented).${lifeAtRisk > 0 ? ` ${lifeAtRisk} at life at risk.` : ""}`;
}

/**
 * The one-line notice when a step forward brings invented items: "New exercise call (1)", "New exercise report (2)",
 * or "New exercise items (3)" for both kinds. `paused` adds that playback stopped for a life-at-risk item.
 */
export function commandNewItemsNotice(calls: number, reports: number, paused: boolean, language: Language): string {
  const total = calls + reports;
  const th = language === "th";
  const what = reports === 0
    ? th ? "ฝึกซ้อม: มีการขอความช่วยเหลือใหม่" : "New exercise call"
    : calls === 0
      ? th ? "ฝึกซ้อม: มีรายงานใหม่" : "New exercise report"
      : th ? "ฝึกซ้อม: มีรายการใหม่" : "New exercise items";
  const tail = paused ? (th ? " · หยุดการเล่นชั่วคราว" : " · replay paused") : "";
  return `${what} (${total})${tail}`;
}

// --- Markers of the map ----------------------------------------------------------------------------------

export const COMMAND_MARKERS = {
  recordsLayer: { en: "Place records and exercise items", th: "รายการตามสถานที่และรายการฝึกซ้อม" },
  modelDry: { en: "model dry at the point", th: "แบบจำลองแห้งที่จุดนี้" },
  modelDryMeaning: {
    en: "The model shows dry ground at this point over the time the report describes. The report is not wrong because of that: the model is low confidence.",
    th: "แบบจำลองแสดงว่าจุดนี้ไม่มีน้ำในช่วงเวลาที่รายงานกล่าวถึง ซึ่งไม่ได้แปลว่ารายงานผิด เพราะแบบจำลองมีความเชื่อมั่นต่ำ",
  },
  noReports: { en: "no reports received", th: "ยังไม่ได้รับรายงาน" },
  noReportsMeaning: {
    en: "Residents are in modelled water here, and no place record or exercise item has come in by this replay hour. Silence is not safety.",
    th: "ตำบลนี้มีผู้อยู่อาศัยในน้ำตามแบบจำลอง แต่ยังไม่มีรายการตามสถานที่หรือรายการฝึกซ้อมเข้ามาถึงชั่วโมงนี้ของการย้อนดู การไม่มีรายงานไม่ได้แปลว่าปลอดภัย",
  },
  siteNotYet: { en: "Not yet reported at this replay hour", th: "ยังไม่มีรายงาน ณ ชั่วโมงนี้ของการย้อนดู" },
  clusterZoom: { en: "Select to zoom in", th: "เลือกเพื่อขยายแผนที่" },
  tolerance: { en: "stated tolerance of the selected place", th: "ระยะคลาดเคลื่อนของสถานที่ที่เลือก" },
  envelope: { en: "2024 season envelope (scenario)", th: "ขอบเขตน้ำตลอดฤดูปี 2567 (2024) (สถานการณ์จำลอง)" },
} as const satisfies Record<string, Localized>;

/** The legend of the reports: the marker grammar as a grid. */
export const COMMAND_LEGEND_REPORTS = {
  records: { en: "Place records (news, not surveyed)", th: "รายการตามสถานที่ (จากข่าว ไม่ได้สำรวจ)" },
  bubble: { en: "2024 place records at a point, with their count", th: "รายการตามสถานที่ปี 2567 (2024) ณ จุดนั้น พร้อมจำนวน" },
  exercise: { en: "Exercise items (invented)", th: "รายการฝึกซ้อม (สมมุติขึ้น)" },
  /** The two rows of the grid: the shape says the kind of an item. */
  rowCall: { en: "call for help", th: "ขอความช่วยเหลือ" },
  rowReport: { en: "depth or road report", th: "รายงานระดับน้ำหรือถนน" },
  stateNew: { en: "dashed: new", th: "เส้นประ: ใหม่" },
  stateSolid: { en: "solid: acknowledged or assigned", th: "เส้นทึบ: รับทราบหรือมอบหมายแล้ว" },
  stateClosed: { en: "grey, tick: done or dropped", th: "สีเทา มีเครื่องหมายถูก: เสร็จสิ้นหรือยุติ" },
  waiting: {
    en: "under every item: EX (invented), then the callsign and the hours waited in replay time",
    th: "ใต้ทุกรายการ: EX (สมมุติขึ้น) ตามด้วยนามเรียกขานและชั่วโมงที่รอตามเวลาในการย้อนดู",
  },
  other: { en: "Other marks", th: "เครื่องหมายอื่น" },
  device: { en: "reports saved on this device (dated when saved; outside the replay)", th: "รายงานที่บันทึกไว้ในอุปกรณ์เครื่องนี้ (ลงวันที่ที่บันทึก ไม่อยู่ในการย้อนดู)" },
  noReports: {
    en: "residents in modelled water and no report by this hour; silence is not safety",
    th: "มีผู้อยู่อาศัยในน้ำตามแบบจำลอง แต่ยังไม่มีรายงานถึงชั่วโมงนี้ การไม่มีรายงานไม่ได้แปลว่าปลอดภัย",
  },
  cluster: {
    en: "count mark: place records above, invented items (EX) below; \u201c!!\u201d counts those at life at risk",
    th: "เครื่องหมายรวม: บนคือรายการตามสถานที่ ล่างคือรายการฝึกซ้อม (EX สมมุติขึ้น) \u201c!!\u201d คือจำนวนที่เสี่ยงต่อชีวิต",
  },
  sitePending: { en: "shelter not yet reported at this hour", th: "ที่พักพิงที่ยังไม่มีรายงาน ณ ชั่วโมงนี้" },
  urgencyRule: {
    en: "Urgency is set by the author of an invented item from the facts it states, never by the model. The colours are not those of medical triage.",
    th: "ผู้เขียนรายการสมมุติกำหนดระดับความเร่งด่วนจากข้อเท็จจริงที่รายการระบุ แบบจำลองไม่ได้เป็นผู้กำหนด และสีที่ใช้ไม่ใช่สีของการคัดแยกผู้ป่วย",
  },
} as const satisfies Record<string, Localized>;

/**
 * What a count mark of the district zoom holds, in words: "11 place records · 11 exercise items (invented), 2 at life
 * at risk". The two kinds are counted apart and never added: invented items are not reports of 2024.
 */
export function commandClusterCounts(records: number, items: number, lifeAtRisk: number, language: Language): string {
  const th = language === "th";
  const parts: string[] = [];
  if (records > 0) parts.push(th ? `รายการตามสถานที่ ${records} รายการ` : `${records} place ${records === 1 ? "record" : "records"}`);
  if (items > 0) {
    const life = lifeAtRisk > 0 ? (th ? ` เสี่ยงต่อชีวิต ${lifeAtRisk} รายการ` : `, ${lifeAtRisk} at life at risk`) : "";
    parts.push(th ? `รายการฝึกซ้อม (สมมุติขึ้น) ${items} รายการ${life}` : `${items} exercise ${items === 1 ? "item" : "items"} (invented)${life}`);
  }
  return parts.join(" · ");
}

/** The accessible name of a count mark: what it holds, then "Select to zoom in." */
export function commandClusterTitle(records: number, items: number, lifeAtRisk: number, language: Language): string {
  const zoom = pick(COMMAND_MARKERS.clusterZoom, language);
  const counts = commandClusterCounts(records, items, lifeAtRisk, language);
  return language === "th" ? `${counts} ${zoom}` : `${counts}. ${zoom}.`;
}

// --- Reports saved on this device ------------------------------------------------------------------------

export const COMMAND_DEVICE = {
  title: { en: "Reports saved on this device", th: "รายงานที่บันทึกไว้ในอุปกรณ์เครื่องนี้" },
  notSent: { en: "Saved by the Public page in this browser. Nothing was sent to anyone.", th: "บันทึกจากหน้าประชาชนในเบราว์เซอร์นี้ และไม่ได้ส่งให้ผู้ใด" },
  noPoint: {
    en: "A report names a subdistrict and no point, so the model depth is not looked up.",
    th: "รายงานระบุเพียงตำบล ไม่มีจุดบนแผนที่ จึงไม่ได้อ่านค่าความลึกจากแบบจำลอง",
  },
  note: { en: "Show the note", th: "แสดงบันทึกข้อความ" },
  noteRule: { en: "A note stays on this device and never enters a brief or an export.", th: "บันทึกข้อความเก็บไว้ในอุปกรณ์เครื่องนี้เท่านั้น ไม่นำไปใส่ในข้อความสรุปหรือไฟล์ส่งออก" },
  photo: { en: "a photo was attached (the image file is not stored)", th: "มีการแนบรูปภาพ (ไม่ได้เก็บไฟล์ภาพ)" },
  depth: { en: "Depth", th: "ระดับน้ำ" },
} as const satisfies Record<string, Localized>;

/** The sign on a subdistrict's name: "2 · this device" / "2 · เครื่องนี้". */
export function commandDeviceSign(count: number, language: Language): string {
  return language === "th" ? `${count} · เครื่องนี้` : `${count} · this device`;
}

/**
 * The line every device sign carries: "This device · 5 Oct 2026 · not part of the 2024 replay · tambon (subdistrict) only".
 * `savedAt` is the instant the newest report was saved; it is a date of today's world, so it never sits on the replay clock.
 */
export function commandDeviceMeta(savedAt: string, language: Language): string {
  const date = formatDateWithYear(savedAt, language);
  return language === "th"
    ? `อุปกรณ์เครื่องนี้ · ${date} · ไม่ใช่ส่วนหนึ่งของการย้อนดูเหตุการณ์ปี 2567 (2024) · ระบุเพียงระดับตำบล`
    : `This device · ${date} · not part of the 2024 replay · tambon (subdistrict) only`;
}

/** "2 reports saved" / "บันทึกไว้ 2 รายงาน". Counted things keep plain digits. */
export function commandDeviceCount(count: number, language: Language): string {
  if (language === "th") return `บันทึกไว้ ${count} รายงาน`;
  return `${count} ${count === 1 ? "report" : "reports"} saved`;
}

/** What the sign says to a screen reader: the count, the subdistrict, and that it is outside the replay. */
export function commandDeviceSignTitle(count: number, tambon: Localized, language: Language): string {
  return language === "th"
    ? `${pick(COMMAND_DEVICE.title, language)}: ${count} รายงาน ต.${tambon.th} · ไม่ใช่ส่วนหนึ่งของการย้อนดูเหตุการณ์ปี 2567 (2024)`
    : `${pick(COMMAND_DEVICE.title, language)}: ${count} in ${tambon.en} subdistrict · not part of the 2024 replay`;
}

// --- The two modes ---------------------------------------------------------------------------------------

export const COMMAND_MODE = {
  label: { en: "What the exercise shows of the future", th: "การแสดงสิ่งที่ยังไม่เกิดขึ้น ณ ชั่วโมงนี้" },
  trainee: { en: "Trainee", th: "ผู้เข้ารับการฝึก" },
  hindsight: { en: "Hindsight", th: "มองย้อนหลัง" },
  traineeLine: { en: "Trainee mode · the future is hidden", th: "โหมดผู้เข้ารับการฝึก · ซ่อนสิ่งที่ยังไม่เกิดขึ้น" },
  hindsightLine: { en: "Hindsight mode · everything is shown", th: "โหมดมองย้อนหลัง · แสดงทั้งหมด" },
  traineeMeaning: {
    en: "Place records appear when their article was published, and the list holds nothing of a later hour.",
    th: "รายการตามสถานที่จะแสดงเมื่อถึงเวลาที่ข่าวเผยแพร่ และรายการที่ทราบจะไม่มีสิ่งใดจากชั่วโมงที่ยังมาไม่ถึง",
  },
  hindsightMeaning: {
    en: "Everything the replay data holds is shown, with the 2024 season envelope and the cumulative agency figure.",
    th: "แสดงทุกอย่างที่ข้อมูลการย้อนดูมี รวมทั้งขอบเขตน้ำตลอดฤดูปี 2567 (2024) และตัวเลขสะสมของหน่วยงาน",
  },
  /** The switch of the time dock is on in trainee mode and off in hindsight mode. */
  switchLabel: { en: "Trainee mode: hide the future", th: "โหมดผู้เข้ารับการฝึก: ซ่อนสิ่งที่ยังไม่เกิดขึ้น" },
  exercise: { en: "Exercise", th: "การฝึกซ้อม" },
  items: { en: "Exercise items", th: "รายการฝึกซ้อม" },
  itemsNote: { en: "Invented calls and reports, each shown from its replay hour", th: "การขอความช่วยเหลือและรายงานที่สมมุติขึ้น แสดงเมื่อถึงชั่วโมงของแต่ละรายการ" },
  pause: { en: "Pause when a life-at-risk item arrives", th: "หยุดการเล่นเมื่อมีรายการเสี่ยงต่อชีวิตเข้ามา" },
  pauseNote: { en: "Playback stops at that replay hour, so the team can act", th: "การเล่นจะหยุดที่ชั่วโมงนั้น เพื่อให้ชุดปฏิบัติการมีเวลาดำเนินการ" },
} as const satisfies Record<string, Localized>;

export const commandModeLine = (mode: CommandMode, language: Language): string => pick(mode === "hindsight" ? COMMAND_MODE.hindsightLine : COMMAND_MODE.traineeLine, language);

// --- "Known by now" --------------------------------------------------------------------------------------

export const COMMAND_FEED = {
  title: { en: "Known by now", th: "ข้อมูลที่ทราบถึงชั่วโมงนี้" },
  /** The fixed first line: what is missing. */
  missing: {
    en: "No public hourly river-level record for the Sai was found.",
    th: "ไม่พบข้อมูลระดับน้ำแม่น้ำสายรายชั่วโมงที่เปิดเผยต่อสาธารณะ",
  },
  missingTag: { en: "Missing", th: "ไม่มีข้อมูล" },
  empty: { en: "Nothing had been reported or observed by this replay hour.", th: "ยังไม่มีสิ่งใดที่มีรายงานหรือสังเกตได้ถึงชั่วโมงนี้ของการย้อนดู" },
  noRecordsYet: { en: "No place record with a point by this replay hour.", th: "ยังไม่มีรายการตามสถานที่ที่มีจุดบนแผนที่ถึงชั่วโมงนี้ของการย้อนดู" },
  groupStart: { en: "Held at the start of the replay", th: "มีอยู่แล้วตั้งแต่เริ่มการย้อนดู" },
  groupEvent: { en: "Whole event · hindsight only", th: "ตลอดเหตุการณ์ · เฉพาะโหมดมองย้อนหลัง" },
  groupAfter: { en: "After the replay ends · hindsight only", th: "หลังสิ้นสุดการย้อนดู · เฉพาะโหมดมองย้อนหลัง" },
  showOnMap: { en: "Show on the map", th: "แสดงบนแผนที่" },
  source: { en: "Source", th: "แหล่งข้อมูล" },
  later: { en: "later than this replay hour", th: "หลังชั่วโมงนี้ของการย้อนดู" },
  thisHour: { en: "at this replay hour", th: "ในชั่วโมงนี้ของการย้อนดู" },
  dayOnly: { en: "day only: the hour is not known", th: "ทราบเพียงวันที่ ไม่ทราบเวลา" },
  dayEnd: { en: "The article gives a date and no time, so it is listed from the end of that day.", th: "ข่าวระบุเพียงวันที่ ไม่ระบุเวลา จึงแสดงเมื่อสิ้นวันนั้น" },
  noTime: { en: "no time in the data", th: "ข้อมูลไม่ระบุเวลา" },
  beforeReplay: { en: "before the replay starts", th: "ก่อนเริ่มการย้อนดู" },
  rainRule: {
    en: "Listed when an hour reaches 10 mm: a display rule, not a hazard level.",
    th: "แสดงเมื่อฝนรายชั่วโมงถึง 10 มม. เป็นเกณฑ์การแสดงผล ไม่ใช่ระดับอันตราย",
  },
  passLater: { en: "would have reached responders later", th: "ผู้ปฏิบัติงานจะได้รับภาพช้ากว่านี้" },
  passTuned: {
    en: "Used to tune the model as the water fell, so agreement with it is not independent evidence.",
    th: "ใช้ปรับแบบจำลองช่วงน้ำลด ความสอดคล้องกับภาพนี้จึงไม่ใช่หลักฐานอิสระ",
  },
  viirsNote: { en: "Nominal 13:30 pass. The map itself is not drawn on this page.", th: "ดาวเทียมผ่านเวลาประมาณ 13:30 น. หน้านี้ไม่แสดงแผนที่ดังกล่าว" },
  radarsatNote: { en: "Calibration: used to set the model. Acquired at this time and published later.", th: "ใช้ปรับแบบจำลอง: ภาพบันทึก ณ เวลานี้ และเผยแพร่ภายหลัง" },
  unosatNote: {
    en: "Preliminary, not field-validated. A cumulative figure that was known while the model was tuned; the data holds no publication time.",
    th: "ผลเบื้องต้น ยังไม่ผ่านการตรวจสอบภาคสนาม เป็นตัวเลขสะสมที่ทราบอยู่แล้วขณะปรับแบบจำลอง และข้อมูลไม่ระบุเวลาเผยแพร่",
  },
  sheltersNote: { en: "Reported, not surveyed. The time it came into use that day is not known.", th: "ตามรายงาน ไม่ได้สำรวจ ไม่ทราบเวลาที่เริ่มใช้ในวันนั้น" },
  recordNote: { en: "Reported in news, not surveyed.", th: "ตามรายงานข่าว ไม่ได้สำรวจ" },
  modelNote: { en: "An event of the model, low confidence; nobody observed it.", th: "เหตุการณ์ในแบบจำลอง ความเชื่อมั่นต่ำ ไม่ได้มาจากการสังเกตการณ์" },
  credit: { en: "Credit", th: "เครดิต" },
  marks: {
    en: "Event marks: filled for reported or observed items, hollow for events of the model",
    th: "เครื่องหมายเหตุการณ์: ทึบคือสิ่งที่มีรายงานหรือสังเกตได้ โปร่งคือเหตุการณ์ในแบบจำลอง",
  },
} as const satisfies Record<string, Localized>;

/** "Known by now (12)" / "ข้อมูลที่ทราบถึงชั่วโมงนี้ (12)": the chip and the tab, with the number of rows. */
export function commandKnownCount(label: Localized, count: number, language: Language): string {
  return `${pick(label, language)} (${count})`;
}

/** "Jump to newest (3)" / "ไปที่รายการล่าสุด (3)". */
export function commandFeedJump(count: number, language: Language): string {
  return language === "th" ? `ไปที่รายการล่าสุด (${count})` : `Jump to newest (${count})`;
}

/** The heading of a group of rows: a local day, the start of the replay, or the whole event. */
export function commandFeedGroupTitle(key: string, language: Language): string {
  if (key === "start") return pick(COMMAND_FEED.groupStart, language);
  if (key === "event") return pick(COMMAND_FEED.groupEvent, language);
  if (key === "after") return pick(COMMAND_FEED.groupAfter, language);
  return formatDateWithYear(key, language);
}

const instantOf = (time: number): string => new Date(TIMELINE_EPOCH_MS + time * 3_600_000).toISOString();
const dateOf = (time: number): string => new Date(TIMELINE_EPOCH_MS + time * 3_600_000 + 7 * 3_600_000).toISOString().slice(0, 10);
const km2 = (value: number, language: Language): string => `${value} ${language === "th" ? "ตร.กม." : "km²"}`;
const joinNames = (names: readonly string[], language: Language): string => {
  if (language === "th" || names.length < 2) return names.join(" ");
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
};

/** The time of a row as the data gives it: "10 Sep 05:32 ICT", "11 Sep" for a date only, or that the data holds none. */
export function commandFeedTime(item: Pick<CommandFeedItem, "time" | "precision">, language: Language): string {
  if (item.time === null) return pick(COMMAND_FEED.noTime, language);
  if (item.precision === "day") return formatShortDate(dateOf(item.time), language);
  if (item.precision === "day_end") return formatShortDate(dateOf(item.time - 1), language);
  return formatLocalStamp(instantOf(item.time), language);
}

/**
 * How long before the replay hour a row is dated: "3 h earlier", "2 days earlier", "at this replay hour"; in
 * hindsight a later row reads "later than this replay hour". Null for a row without a time in the replay.
 */
export function commandFeedAge(item: Pick<CommandFeedItem, "time" | "fromHour" | "precision">, hour: number, language: Language): string | null {
  if (item.time === null || item.time > COMMAND_LAST_HOUR) return null;
  if (item.precision === "held") return pick(COMMAND_FEED.beforeReplay, language);
  if (item.fromHour > hour) return pick(COMMAND_FEED.later, language);
  const hours = Math.floor(hour - item.time);
  if (hours < 1) return pick(COMMAND_FEED.thisHour, language);
  if (hours < 48) return language === "th" ? `${hours} ชม. ก่อนหน้านี้` : `${hours} h earlier`;
  const days = Math.floor(hours / 24);
  return language === "th" ? `${days} วันก่อนหน้านี้` : `${days} days earlier`;
}

/** The headline of a row. Counts of things keep plain digits; a modelled figure is rounded like every other. */
export function commandFeedHeadline(item: Pick<CommandFeedItem, "detail" | "places" | "time">, depths: Pick<ReportedDepths, "depth_classes"> | null, language: Language): string {
  const th = language === "th";
  const { detail } = item;
  switch (detail.kind) {
    case "place_record": {
      const names = joinNames(item.places.map((place) => pick(place, language)), language);
      const depth = depths ? reportedDepthText(detail.reports[0], depths, language) : pick(detail.reports[0].depth.statement, language);
      return `${names}: ${depth}`;
    }
    case "rain": {
      const to = item.time === null ? "" : formatHourStamp(item.time, language).split(" ").slice(2).join(" ");
      return th
        ? `ฝน ${detail.mm.toFixed(1)} มม. ในชั่วโมงก่อน ${to} ที่สถานี ${detail.station.name_th}`
        : `${detail.mm.toFixed(1)} mm of rain in the hour to ${to} at the gauge ${detail.station.name_en}`;
    }
    case "satellite": {
      const image = detail.observation.kind === "radar" ? (th ? "ภาพเรดาร์ Sentinel-1" : "Sentinel-1 radar image") : (th ? "ภาพ Sentinel-2" : "Sentinel-2 image");
      const stamp = formatLocalStamp(detail.observation.local, language);
      if (detail.preEvent) return th ? `${image} ของวันที่ ${stamp}: มีอยู่แล้วตั้งแต่เริ่มการย้อนดู` : `${image} of ${stamp}: held at the start`;
      return th ? `${image} บันทึกเมื่อ ${stamp} · ${pick(COMMAND_FEED.passLater, language)}` : `${image} acquired ${stamp}; ${pick(COMMAND_FEED.passLater, language)}`;
    }
    case "viirs": {
      const share = Math.round(detail.cloudShare * 100);
      return th ? `แผนที่น้ำท่วมรายวันจาก VIIRS: เมฆปกคลุม ${share}% ของอำเภอ` : `VIIRS daily flood map: ${share}% of the district under cloud`;
    }
    case "radarsat":
      return th
        ? `ผลวิเคราะห์น้ำท่วมจาก RADARSAT-2 ของ GISTDA: พื้นที่น้ำ ${km2(detail.km2, language)} ในอำเภอแม่สาย`
        : `GISTDA RADARSAT-2 flood analysis: ${km2(detail.km2, language)} of water in Mae Sai district`;
    case "unosat_3991":
      return th
        ? `ผลิตภัณฑ์ UNOSAT 3991: พื้นที่น้ำสะสมประมาณ ${km2(detail.km2, language)} ช่วงวันที่ 13–19 ก.ย. 2567 (2024)`
        : `UNOSAT product 3991: about ${km2(detail.km2, language)} of water mapped over 13–19 Sep 2024 (cumulative)`;
    case "season_envelope":
      return th
        ? "ขอบเขตน้ำตลอดฤดูปี 2567 (2024): น้ำที่ทำแผนที่ไว้ ณ เวลาใดเวลาหนึ่งระหว่างเดือนสิงหาคมถึงตุลาคม (สถานการณ์จำลอง)"
        : "2024 season envelope: water mapped at some time from August to October 2024 (scenario)";
    case "shelters": {
      const centre = detail.commandCentres > 0;
      if (th) return `มีรายงานการใช้ที่พักพิง ${detail.shelters} แห่ง${centre ? " และศูนย์บัญชาการเหตุการณ์อำเภอ" : ""}`;
      return `${detail.shelters} ${detail.shelters === 1 ? "shelter" : "shelters"}${centre ? " and the district command centre" : ""} reported in use`;
    }
    case "model_phase":
      return th ? `แบบจำลองเข้าสู่ระยะ: ${detail.label.th}` : `Model phase begins: ${detail.label.en}`;
    case "model_peak":
      return th ? `ระดับแม่น้ำสมมุติสูงสุดในแบบจำลอง: ${detail.stage.toFixed(1)} ม.` : `Highest assumed river stage in the model: ${detail.stage.toFixed(1)} m`;
    case "model_first_loss": {
      const figure = roundModelFigure(detail.lostAccess).text;
      return th
        ? `ต.${detail.tambon.th}: แบบจำลองเริ่มมีผู้อยู่อาศัยสูญเสียการเข้าถึงที่พักพิง (${figure} คน)`
        : `${detail.tambon.en}: residents begin to lose shelter access in the model (${figure})`;
    }
  }
}

/** The second sentence of a row, where its kind has one: what the row is, and what it is not. */
export function commandFeedNote(item: Pick<CommandFeedItem, "detail" | "precision">, language: Language): string | null {
  const { detail } = item;
  switch (detail.kind) {
    case "place_record": return item.precision === "day_end" ? `${pick(COMMAND_FEED.recordNote, language)} ${pick(COMMAND_FEED.dayEnd, language)}` : pick(COMMAND_FEED.recordNote, language);
    case "rain": return pick(COMMAND_FEED.rainRule, language);
    case "satellite": return detail.calibration ? pick(COMMAND_FEED.passTuned, language) : null;
    case "viirs": return pick(COMMAND_FEED.viirsNote, language);
    case "radarsat": return pick(COMMAND_FEED.radarsatNote, language);
    case "unosat_3991": return pick(COMMAND_FEED.unosatNote, language);
    case "season_envelope": return null;
    case "shelters": return pick(COMMAND_FEED.sheltersNote, language);
    default: return pick(COMMAND_FEED.modelNote, language);
  }
}

/**
 * The situation line about the place records known by now: how many have a point, and what the model shows at those
 * points. Before the first located record it says that there is none yet.
 */
export function commandRecordTallyLine(tally: PlaceRecordTally, language: Language): string {
  if (tally.located === 0) return pick(COMMAND_FEED.noRecordsYet, language);
  return language === "th"
    ? `รายการตามสถานที่ที่มีจุดบนแผนที่: ${tally.located} รายการ ที่จุดเหล่านั้นแบบจำลองสอดคล้อง ${tally.consistent} มีน้ำ ${tally.wet} และแห้ง ${tally.dry}`
    : `Place records with a point: ${tally.located}. At the point, the model is consistent with ${tally.consistent}, wet at ${tally.wet} and dry at ${tally.dry}.`;
}

/** The short form beside the model tag of the situation card: "12 place records · model dry at 9". */
export function commandRecordTallyChip(tally: PlaceRecordTally, language: Language): string {
  if (language === "th") return `รายการตามสถานที่ ${tally.located} · แบบจำลองแห้ง ${tally.dry}`;
  return `${tally.located} place ${tally.located === 1 ? "record" : "records"} · model dry at ${tally.dry}`;
}
