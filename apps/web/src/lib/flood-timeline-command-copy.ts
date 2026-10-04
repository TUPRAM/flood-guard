/**
 * Wording of the Command exercise replay (Mae Sai, September 2024) in English and Thai: the banner, the replay clock,
 * the model figures, the lane tags and the information drawer.
 *
 * The page is an exercise and after-action tool for people who coordinate rescue. It replays a reconstructed 2024
 * event; it is not real-time, not an official warning and not a dispatch system, and every modelled figure is low
 * confidence. Each string here is scanned by the shared wording lint (`replay-wording-rules.json`).
 *
 * Thai: no native reviewer was available for the competition build (owner decision, 5 Oct 2026). The Thai text was
 * written in the plain register of Thai public disaster notices, with the terms the replay already uses, and the
 * information drawer says that no native speaker has reviewed it.
 */

import { formatDateWithYear, formatShortDate, TIMELINE_EPOCH_MS, type EvidenceLane, type Language, type Localized } from "./flood-timeline";
import { roadNameText } from "./flood-timeline-copy";
import {
  clampCommandHour,
  COMMAND_LAST_HOUR,
  roundModelChange,
  roundModelFigure,
  roundModelKm,
  type CommandChange,
  type CommandFigures,
  type CommandRoadChange,
} from "./flood-timeline-command";

const pick = (text: Localized, language: Language): string => (language === "th" ? text.th : text.en);

// --- Banner ----------------------------------------------------------------------------------------------

/** The permanent banner: it never collapses and cannot be dismissed. */
export const COMMAND_BANNER = {
  tag: { en: "Exercise replay", th: "ฝึกซ้อมย้อนดูเหตุการณ์" },
  place: { en: "Mae Sai, September 2024", th: "แม่สาย กันยายน 2567 (2024)" },
  nature: { en: "reconstructed, not real-time", th: "จำลองย้อนหลัง ไม่ใช่ข้อมูลเรียลไทม์" },
  notWarning: { en: "not an official warning", th: "ไม่ใช่คำเตือนทางการ" },
  /** Accessible name of the banner. */
  label: { en: "Exercise notice", th: "ข้อความแจ้งว่าเป็นการฝึกซ้อม" },
  /** Accessible name of the (i) button that opens the information drawer. */
  info: {
    en: "About this exercise: permitted use, assumptions, limits, sources and licences",
    th: "เกี่ยวกับการฝึกซ้อมนี้: การใช้งานที่อนุญาต สมมติฐาน ข้อจำกัด แหล่งข้อมูล และสัญญาอนุญาต",
  },
  /** Tiled faintly across the map in both languages at once, so any cropped photo of the screen keeps the label. */
  watermark: { en: "EXERCISE · ฝึกซ้อม", th: "EXERCISE · ฝึกซ้อม" },
} as const satisfies Record<string, Localized>;

/** The four parts of the banner in reading order. */
export function commandBannerParts(language: Language): string[] {
  return [COMMAND_BANNER.tag, COMMAND_BANNER.place, COMMAND_BANNER.nature, COMMAND_BANNER.notWarning].map((part) => pick(part, language));
}

/** The banner as one line: "Exercise replay · Mae Sai, September 2024 · reconstructed, not real-time · not an official warning". */
export function commandBannerLine(language: Language): string {
  return commandBannerParts(language).join(" · ");
}

// --- Replay clock ----------------------------------------------------------------------------------------

export const COMMAND_CLOCK = {
  label: { en: "Replay time", th: "เวลาในการย้อนดู" },
  /** The static tag beside the clock. */
  tag: { en: "Replay", th: "ย้อนดู" },
  tagMeaning: { en: "A time in September 2024, not the time now", th: "เวลาของเหตุการณ์เดือนกันยายน 2567 (2024) ไม่ใช่เวลาปัจจุบัน" },
  phase: { en: "Phase", th: "ระยะ" },
  stage: { en: "assumed river stage", th: "ระดับแม่น้ำสมมุติ" },
  stageNote: { en: "illustrative curve", th: "ค่าเพื่อการอธิบาย" },
  stageMeaning: {
    en: "The assumed level of the Sai River at the Mae Sai border bridges, in metres above the mapped channel. No public hourly record for September 2024 was found, so the curve is illustrative.",
    th: "ระดับแม่น้ำสายสมมุติที่สะพานข้ามแดนแม่สาย เป็นเมตรเหนือร่องน้ำในแผนที่ ไม่พบข้อมูลรายชั่วโมงที่เปิดเผยสำหรับเดือนกันยายน 2567 (2024) จึงเป็นค่าเพื่อการอธิบาย",
  },
} as const satisfies Record<string, Localized>;

/** Local date (ICT) and clock hour of a replay hour; the end of the replay, 20 Sep 00:00, reads as 24:00 on 19 Sep. */
function replayClock(hour: number): { date: string; time: string } {
  const at = clampCommandHour(hour);
  const end = at >= COMMAND_LAST_HOUR;
  const local = new Date(TIMELINE_EPOCH_MS + (end ? at - 1 : at) * 3_600_000 + 7 * 3_600_000);
  return { date: local.toISOString().slice(0, 10), time: `${String(end ? 24 : local.getUTCHours()).padStart(2, "0")}:00` };
}

/**
 * The replay time as the clock prints it, the largest text of the page: "12 Sep 2024 · 12:00 ICT" /
 * "12 ก.ย. 2567 (2024) · 12:00 น." (Western digits, 24-hour time, the Buddhist year with the CE year in brackets).
 */
export function commandMoment(hour: number, language: Language): string {
  const { date, time } = replayClock(hour);
  return `${formatDateWithYear(date, language)} · ${time}${language === "th" ? " น." : " ICT"}`;
}

/** The short form for a narrow or collapsed card: "12 Sep 12:00 ICT" / "12 ก.ย. 12:00 น.". */
export function commandMomentShort(hour: number, language: Language): string {
  const { date, time } = replayClock(hour);
  return `${formatShortDate(date, language)} ${time}${language === "th" ? " น." : " ICT"}`;
}

/** "hour 84 of 264" / "ชั่วโมงที่ 84 จาก 264". */
export function commandHourOf(hour: number, language: Language): string {
  return language === "th" ? `ชั่วโมงที่ ${hour} จาก ${COMMAND_LAST_HOUR}` : `hour ${hour} of ${COMMAND_LAST_HOUR}`;
}

/** The short form for a collapsed card: "h 84" / "ชม. 84". */
export function commandHourShort(hour: number, language: Language): string {
  return language === "th" ? `ชม. ${hour}` : `h ${hour}`;
}

/** The assumed stage as the clock prints it: "3.5 m", "<0.1 m" for a trace, "0 m" when the river is at its channel. */
export function commandStageText(stage: number, language: Language): string {
  const unit = language === "th" ? "ม." : "m";
  if (!(stage > 0)) return `0 ${unit}`;
  return stage < 0.05 ? `<0.1 ${unit}` : `${stage.toFixed(1)} ${unit}`;
}

/** "Phase: Peak · assumed river stage 3.5 m (illustrative curve)"; `phaseLabel` is the manifest's own label. */
export function commandPhaseLine(phaseLabel: Localized, stage: number, language: Language): string {
  return `${pick(COMMAND_CLOCK.phase, language)}: ${pick(phaseLabel, language)} · ${pick(COMMAND_CLOCK.stage, language)} ${commandStageText(stage, language)} (${pick(COMMAND_CLOCK.stageNote, language)})`;
}

// --- Model figures ---------------------------------------------------------------------------------------

export const COMMAND_FIGURES = {
  label: { en: "Model figures at this replay hour", th: "ตัวเลขจากแบบจำลอง ณ ชั่วโมงนี้ของการย้อนดู" },
  /** The lane tag every modelled figure wears. */
  modelTag: { en: "Model · low confidence", th: "แบบจำลอง · ความเชื่อมั่นต่ำ" },
  lostAccess: { en: "lost shelter access", th: "สูญเสียการเข้าถึงที่พักพิง" },
  lostAccessMeaning: {
    en: "Residents who could walk to a shelter of the chosen set within 2 km on passable roads before the flood, and cannot at this replay hour. It is not a count of people stranded.",
    th: "ผู้อยู่อาศัยที่ก่อนน้ำท่วมเดินไปถึงที่พักพิงในชุดที่เลือกได้ภายใน 2 กม. บนถนนที่สัญจรได้ แต่ ณ ชั่วโมงนี้ของการย้อนดูเดินไปไม่ถึงแล้ว ตัวเลขนี้ไม่ใช่จำนวนผู้ติดค้าง",
  },
  scope: { en: "Counted over all residents at road nodes.", th: "นับจากผู้อยู่อาศัยทั้งหมดที่จุดถนน" },
  inWater: { en: "residents in modelled water", th: "ผู้อยู่อาศัยในน้ำตามแบบจำลอง" },
  inWaterMeaning: {
    en: "Residents whose home cell is in modelled water. Residents are WorldPop 2020, not the 2024 population.",
    th: "ผู้อยู่อาศัยที่ตำแหน่งบ้านอยู่ในน้ำตามแบบจำลอง จำนวนผู้อยู่อาศัยมาจาก WorldPop 2020 ไม่ใช่ประชากรปี 2567 (2024)",
  },
  roads: { en: "roads impassable", th: "ถนนสัญจรไม่ได้" },
  roadsMeaning: {
    en: "Road length where the modelled water reaches 0.3 m. Bridge decks are not modelled.",
    th: "ความยาวถนนที่น้ำตามแบบจำลองลึกถึง 0.3 ม. ไม่ได้จำลองพื้นสะพาน",
  },
  exerciseItems: { en: "open exercise items", th: "รายการฝึกซ้อมที่ยังเปิดอยู่" },
  exerciseTag: { en: "Exercise · invented", th: "ฝึกซ้อม · สมมุติขึ้น" },
  noExerciseItems: { en: "No exercise items yet", th: "ยังไม่มีรายการฝึกซ้อม" },
  /** Shown in the Receding and Mostly receded phases. */
  modelLimit: {
    en: "The model dries as the river falls; standing water and mud are not reconstructed.",
    th: "แบบจำลองแห้งตามระดับแม่น้ำที่ลดลง ไม่ได้จำลองน้ำท่วมขังและโคลนที่ค้างอยู่",
  },
  changeLost: { en: "lost access", th: "สูญเสียการเข้าถึง" },
  changeWater: { en: "in water", th: "ในน้ำ" },
  changeRoads: { en: "km impassable", th: "กม. สัญจรไม่ได้" },
  noChange: { en: "no change in the model figures", th: "ตัวเลขจากแบบจำลองไม่เปลี่ยน" },
  firstHour: { en: "Start of the replay: no hour before to compare with", th: "เริ่มการย้อนดู: ยังไม่มีชั่วโมงก่อนหน้าให้เทียบ" },
} as const satisfies Record<string, Localized>;

const km = (language: Language): string => (language === "th" ? "กม." : "km");

/** The base of "lost shelter access": "of ~34,500 who had one in reach", or the short "of ~34,500 in reach". */
export function commandBaseText(withinReachBefore: number, language: Language, short = false): string {
  const base = roundModelFigure(withinReachBefore).text;
  if (language === "th") return short ? `จาก ${base} คนในระยะเดิน` : `จาก ${base} คนที่เดินถึงที่พักพิงได้ก่อนน้ำท่วม`;
  return short ? `of ${base} in reach` : `of ${base} who had one in reach`;
}

/** One cell of the figures row: the rounded value, its caption, the line under it and the sentence behind it. */
export interface CommandFigureCell {
  id: "lostAccess" | "inWater" | "roads";
  value: string;
  caption: string;
  /** The base or total the value is part of; null when the figure has none. */
  sub: string | null;
  meaning: string;
}

/**
 * The three model figures as the situation card prints them, e.g. "~7,100 · lost shelter access · of ~34,500 in reach",
 * "~16,100 · residents in modelled water" and "~164 km · roads impassable · of 307 km". The shipped road total is a
 * length of data, not a model result, so it carries no tilde.
 */
export function commandFigureCells(figures: CommandFigures, language: Language): CommandFigureCell[] {
  const total = Math.round(figures.roadKmTotal).toLocaleString("en-US");
  return [
    {
      id: "lostAccess",
      value: roundModelFigure(figures.lostAccess).text,
      caption: pick(COMMAND_FIGURES.lostAccess, language),
      sub: commandBaseText(figures.withinReachBefore, language, true),
      meaning: `${pick(COMMAND_FIGURES.lostAccessMeaning, language)} ${pick(COMMAND_FIGURES.scope, language)}`,
    },
    {
      id: "inWater",
      value: roundModelFigure(figures.inWater).text,
      caption: pick(COMMAND_FIGURES.inWater, language),
      sub: null,
      meaning: pick(COMMAND_FIGURES.inWaterMeaning, language),
    },
    {
      id: "roads",
      value: `${roundModelKm(figures.roadKmImpassable).text} ${km(language)}`,
      caption: pick(COMMAND_FIGURES.roads, language),
      sub: language === "th" ? `จาก ${total} กม.` : `of ${total} km`,
      meaning: pick(COMMAND_FIGURES.roadsMeaning, language),
    },
  ];
}

/** Counted exercise items keep plain digits: "3 open" / "เปิดอยู่ 3", and "1 life at risk" / "เสี่ยงต่อชีวิต 1". */
export function commandOpenItems(open: number, language: Language): string {
  return language === "th" ? `เปิดอยู่ ${open}` : `${open} open`;
}
export function commandLifeAtRisk(count: number, language: Language): string {
  return language === "th" ? `เสี่ยงต่อชีวิต ${count}` : `${count} life at risk`;
}

/**
 * The sentence the situation card may carry about the place records: how many have a point, and what the model shows
 * at those points, so nobody trusts the smooth water layer over a person's report.
 */
export function commandPlaceRecordLine(counts: { located: number; consistent: number; wet: number; dry: number }, language: Language): string {
  return language === "th"
    ? `รายการตามสถานที่ที่มีจุดบนแผนที่: ${counts.located} รายการ ที่จุดเหล่านั้นแบบจำลองสอดคล้อง ${counts.consistent} มีน้ำ ${counts.wet} และแห้ง ${counts.dry}`
    : `Place records with a point: ${counts.located}. At the point, the model is consistent with ${counts.consistent}, wet at ${counts.wet} and dry at ${counts.dry}.`;
}

/** A road name for the line: the known English label in English, the mapped name otherwise. */
const roadLabel = (road: Pick<CommandRoadChange, "name">, language: Language): string => roadNameText(road.name, language).primary;

/** "Phahonyothin Rd (Hwy 1), Mae Sai bypass and 2 more" / "ถนนพหลโยธิน ถนนเลี่ยงเมืองแม่สาย และอีก 2 สาย". */
export function commandRoadList(roads: readonly Pick<CommandRoadChange, "name">[], language: Language, limit = 2): string {
  const shown = roads.slice(0, limit).map((road) => roadLabel(road, language));
  const more = roads.length - shown.length;
  if (language === "th") return more > 0 ? `${shown.join(" ")} และอีก ${more} สาย` : shown.join(" ");
  return more > 0 ? `${shown.join(", ")} and ${more} more` : shown.join(", ");
}

/** The "what changed" line in parts, so the card can lay it out; `text` is the same line as one string. */
export interface CommandChangeLine {
  /** "Since 12 Sep 11:00" or the first-hour sentence. */
  lead: string;
  /** "+~100 lost access", "0 in water", "+~1 km impassable"; empty when nothing moved. */
  figures: string[];
  /** Named roads cut for the first time, or passable again; null when there is none. */
  roads: string | null;
  text: string;
}

/**
 * What changed since the hour before, as the situation card says it. `sinceText` is the hour compared with, already
 * formatted (e.g. `formatHourStamp(change.sinceHour, language)`). Differences are rounded like the figures; only roads
 * newly impassable as a whole road (or passable again as a whole) are named.
 */
export function commandChangeLine(change: CommandChange, sinceText: string, language: Language, roadLimit = 2): CommandChangeLine {
  if (change.sinceHour === null) {
    const lead = pick(COMMAND_FIGURES.firstHour, language);
    return { lead, figures: [], roads: null, text: lead };
  }
  const lead = language === "th" ? `ตั้งแต่ ${sinceText}` : `Since ${sinceText}`;
  const lost = roundModelChange(change.lostAccess);
  const water = roundModelChange(change.inWater);
  const roadKm = roundModelChange(change.roadKmImpassable, roundModelKm);
  const moved = lost.direction !== 0 || water.direction !== 0 || roadKm.direction !== 0;
  const figures = moved
    ? [
        `${lost.text} ${pick(COMMAND_FIGURES.changeLost, language)}`,
        `${water.text} ${pick(COMMAND_FIGURES.changeWater, language)}`,
        `${roadKm.text} ${pick(COMMAND_FIGURES.changeRoads, language)}`,
      ]
    : [];
  const cut = change.newlyImpassable.named.filter((road) => road.whole);
  const open = change.passableAgain.named.filter((road) => road.whole);
  const roadParts = [
    ...(cut.length > 0 ? [`${language === "th" ? "ถนนที่เริ่มสัญจรไม่ได้" : "newly impassable"}: ${commandRoadList(cut, language, roadLimit)}`] : []),
    ...(open.length > 0 ? [`${language === "th" ? "ถนนที่กลับมาสัญจรได้" : "passable again"}: ${commandRoadList(open, language, roadLimit)}`] : []),
  ];
  const roads = roadParts.length > 0 ? roadParts.join(" · ") : null;
  const body = moved ? figures.join(" · ") : pick(COMMAND_FIGURES.noChange, language);
  return { lead, figures, roads, text: `${lead}: ${body}${roads ? ` · ${roads}` : ""}` };
}

// --- Lane tags -------------------------------------------------------------------------------------------

/** The kind of evidence an item is. Every item on the page wears its lane as a short tag. */
export type CommandLane = "model" | "observed" | "reported" | "calibration" | "scenario" | "context" | "exercise" | "device";
export const COMMAND_LANE_ORDER: readonly CommandLane[] = ["model", "observed", "reported", "calibration", "scenario", "context", "exercise", "device"];

export const COMMAND_LANES: Readonly<Record<CommandLane, { tag: Localized; meaning: Localized }>> = {
  model: {
    tag: { en: "Model", th: "แบบจำลอง" },
    meaning: {
      en: "Computed on the reconstructed water with stated assumptions. Low confidence; not an observation.",
      th: "คำนวณจากน้ำที่จำลองขึ้นตามสมมติฐานที่ระบุ ความเชื่อมั่นต่ำ ไม่ใช่การสังเกตการณ์",
    },
  },
  observed: {
    tag: { en: "Observed", th: "สังเกตการณ์" },
    meaning: {
      en: "A dated measurement or image, used as provided and shown beside the model.",
      th: "ค่าที่ตรวจวัดหรือภาพที่มีวันเวลากำกับ ใช้ตามที่ได้รับและแสดงคู่กับแบบจำลอง",
    },
  },
  reported: {
    tag: { en: "Reported", th: "ตามรายงาน" },
    meaning: {
      en: "From news and public reports of 2024, paraphrased. Anecdotal, not surveyed.",
      th: "จากข่าวและรายงานสาธารณะปี 2567 (2024) เรียบเรียงใหม่ เป็นคำบอกเล่า ไม่ได้สำรวจ",
    },
  },
  calibration: {
    tag: { en: "Calibration", th: "ใช้ปรับแบบจำลอง" },
    meaning: {
      en: "A figure used to tune the model, or known while it was tuned. Agreement with it is not independent evidence.",
      th: "ตัวเลขที่ใช้ปรับแบบจำลอง หรือทราบอยู่แล้วขณะปรับ ความสอดคล้องกับตัวเลขนี้จึงไม่ใช่หลักฐานอิสระ",
    },
  },
  scenario: {
    tag: { en: "Scenario", th: "สถานการณ์จำลอง" },
    meaning: {
      en: "A what-if layer, such as water mapped at some time in the 2024 season. Never an observation for a replay hour.",
      th: "ชั้นข้อมูลแบบสมมุติ เช่น น้ำที่ทำแผนที่ไว้ ณ เวลาใดเวลาหนึ่งในฤดูน้ำปี 2567 (2024) ไม่ใช่การสังเกตการณ์ของชั่วโมงใดในการย้อนดู",
    },
  },
  context: {
    tag: { en: "Context", th: "ข้อมูลประกอบ" },
    meaning: {
      en: "Static reference data, such as boundaries and terrain, with its own date.",
      th: "ข้อมูลอ้างอิงที่ไม่เปลี่ยนตามเวลา เช่น เขตการปกครองและภูมิประเทศ ซึ่งมีวันที่ของตนเอง",
    },
  },
  exercise: {
    tag: { en: "Exercise · invented", th: "ฝึกซ้อม · สมมุติขึ้น" },
    meaning: {
      en: "Invented by the team for practice. No real person, call or address; never counted with real reports.",
      th: "ทีมงานสมมุติขึ้นเพื่อการฝึกซ้อม ไม่ใช่บุคคล การขอความช่วยเหลือ หรือที่อยู่จริง และไม่นับรวมกับรายงานจริง",
    },
  },
  device: {
    tag: { en: "This device", th: "อุปกรณ์เครื่องนี้" },
    meaning: {
      en: "Saved in this browser, with today's date. Not part of the 2024 replay and not sent to anyone.",
      th: "บันทึกไว้ในเบราว์เซอร์นี้ ลงวันที่วันนี้ ไม่ใช่ส่วนหนึ่งของการย้อนดูเหตุการณ์ปี 2567 (2024) และไม่ได้ส่งให้ผู้ใด",
    },
  },
};

/** The page's lane for a lane code of the replay data; a cited source the data has not ingested is context. */
export const COMMAND_LANE_OF: Readonly<Record<EvidenceLane, CommandLane>> = {
  SCN: "model", OBS: "observed", REP: "reported", CAL: "calibration", "SCN-ENV": "scenario", CTX: "context", REF: "context",
};

export const commandLaneTag = (lane: CommandLane, language: Language): string => pick(COMMAND_LANES[lane].tag, language);
export const commandLaneMeaning = (lane: CommandLane, language: Language): string => pick(COMMAND_LANES[lane].meaning, language);

// --- Information drawer ----------------------------------------------------------------------------------

/**
 * The drawer behind the banner's (i) button. Its own sentences are here; the permitted use, the assumptions, the
 * limits and the sources are the replay data's sentences, shown under the headings below (Thai through
 * `localizedText` in `flood-timeline-copy`).
 */
export const COMMAND_DRAWER = {
  title: { en: "About this exercise replay", th: "เกี่ยวกับการฝึกซ้อมย้อนดูเหตุการณ์นี้" },
  close: { en: "Close", th: "ปิด" },
  whatTitle: { en: "What this page is", th: "หน้านี้คืออะไร" },
  what: {
    en: "A reconstruction of the September 2024 flood in Mae Sai district, replayed hour by hour from 9 to 19 September (264 hours). People who coordinate rescue use it to practise reading a situation and sharing out teams, and to review the event afterwards.",
    th: "การจำลองย้อนหลังเหตุการณ์น้ำท่วมอำเภอแม่สาย เดือนกันยายน 2567 (2024) ย้อนดูได้ทีละชั่วโมงตั้งแต่วันที่ 9 ถึง 19 กันยายน (264 ชั่วโมง) ผู้ประสานงานกู้ภัยใช้ฝึกอ่านสถานการณ์และจัดสรรชุดปฏิบัติการ และใช้ทบทวนเหตุการณ์ภายหลัง",
  },
  notTitle: { en: "What it is not", th: "หน้านี้ไม่ใช่อะไร" },
  notRealTime: {
    en: "Not real-time. Nothing here shows what is happening now: every hour on the clock is an hour of September 2024.",
    th: "ไม่ใช่ข้อมูลเรียลไทม์ ไม่มีส่วนใดแสดงสิ่งที่กำลังเกิดขึ้นในขณะนี้ ทุกชั่วโมงบนนาฬิกาคือชั่วโมงของเดือนกันยายน 2567 (2024)",
  },
  notWarning: {
    en: "Not an official warning, and not a dispatch system. FloodGuard receives no calls and sends nothing to responders. The hotlines 1784 (disaster), 1669 (medical emergency) and 191 (police) remain the official routes.",
    th: "ไม่ใช่คำเตือนทางการ และไม่ใช่ระบบสั่งการ FloodGuard ไม่รับสายแจ้งเหตุและไม่ส่งข้อมูลถึงหน่วยกู้ภัย สายด่วน 1784 (สาธารณภัย) 1669 (การแพทย์ฉุกเฉิน) และ 191 (ตำรวจ) ยังคงเป็นช่องทางแจ้งเหตุของทางราชการ",
  },
  notOperational: {
    en: "Not for operational decisions. It is for exercises and after-action review; it does not task real teams.",
    th: "ไม่ใช้สำหรับการตัดสินใจในการปฏิบัติการจริง ใช้เพื่อการฝึกซ้อมและการทบทวนหลังเหตุการณ์เท่านั้น และไม่ได้ใช้มอบหมายภารกิจให้ชุดปฏิบัติการจริง",
  },
  notScored: {
    en: "Not a scored case. No priority score and no action class is computed for a replay hour.",
    th: "ไม่ใช่กรณีที่มีการให้คะแนน ไม่มีการคำนวณคะแนนลำดับความสำคัญหรือระดับการดำเนินการสำหรับชั่วโมงใดในการย้อนดู",
  },
  confidenceTitle: { en: "How far to trust the figures", th: "เชื่อตัวเลขได้เพียงใด" },
  confidence: {
    en: "Every modelled figure is low confidence. The river stage is an illustrative curve: no public hourly record of the Sai River for September 2024 was found.",
    th: "ตัวเลขจากแบบจำลองทุกตัวมีความเชื่อมั่นต่ำ ระดับแม่น้ำเป็นเส้นกราฟเพื่อการอธิบาย เพราะไม่พบข้อมูลระดับน้ำแม่น้ำสายรายชั่วโมงที่เปิดเผยสำหรับเดือนกันยายน 2567 (2024)",
  },
  /** The disclosed terrain bias, in the exact words the shared wording rules allow. */
  townBias: {
    en: "The 30 m surface model raises the ground in built-up areas, so modelled water and residents in town are likely underestimated.",
    th: "แบบจำลองพื้นผิวความละเอียด 30 ม. ทำให้ระดับพื้นดินในเขตสิ่งปลูกสร้างสูงกว่าจริง น้ำจากแบบจำลองและจำนวนผู้อยู่อาศัยในน้ำในเขตเมืองจึงน่าจะต่ำกว่าความเป็นจริง",
  },
  rounding: {
    en: "Modelled figures are rounded: a tilde, then the nearest 10 below 1,000 and the nearest 100 above. Counted things, such as exercise items, are plain numbers.",
    th: "ตัวเลขจากแบบจำลองปัดเศษแล้ว: มีเครื่องหมาย ~ นำหน้า ปัดเป็นหลักสิบเมื่อต่ำกว่า 1,000 และเป็นหลักร้อยเมื่อสูงกว่านั้น ส่วนสิ่งที่นับได้จริง เช่น รายการฝึกซ้อม แสดงเป็นตัวเลขตรงตัว",
  },
  lanesTitle: { en: "Kinds of evidence", th: "ประเภทของหลักฐาน" },
  lanesIntro: {
    en: "Every item on the page wears a short tag that says what kind of evidence it is.",
    th: "ทุกรายการในหน้านี้มีป้ายสั้น ๆ บอกว่าเป็นหลักฐานประเภทใด",
  },
  permittedTitle: { en: "Permitted use", th: "การใช้งานที่อนุญาต" },
  deviceTitle: { en: "What stays on this device", th: "ข้อมูลที่เก็บไว้ในอุปกรณ์เครื่องนี้" },
  device: {
    en: "This page sends nothing. What you do in an exercise is stored on this device only.",
    th: "หน้านี้ไม่ส่งข้อมูลใดออกไป สิ่งที่ทำระหว่างการฝึกซ้อมเก็บไว้ในอุปกรณ์เครื่องนี้เท่านั้น",
  },
  thaiTitle: { en: "About the Thai text", th: "เกี่ยวกับข้อความภาษาไทย" },
  thaiNote: {
    en: "The Thai text on this page was written by an AI assistant. It has not been reviewed by a native speaker. Where the two languages differ, the English text is the reference.",
    th: "ข้อความภาษาไทยในหน้านี้เขียนโดยผู้ช่วย AI และยังไม่มีเจ้าของภาษาตรวจทาน หากข้อความสองภาษาไม่ตรงกัน ให้ยึดข้อความภาษาอังกฤษเป็นหลัก",
  },
  /** Beside a sentence of the replay data that has no Thai rendering. */
  englishOriginal: { en: "English original", th: "ต้นฉบับภาษาอังกฤษ" },
} as const satisfies Record<string, Localized>;

/** Headings of the lists the drawer takes from the replay data, with their counts. */
export function commandDrawerHeading(list: "assumptions" | "limits" | "sources", count: number, language: Language): string {
  const names: Record<typeof list, Localized> = {
    assumptions: { en: "Assumptions", th: "สมมติฐาน" },
    limits: { en: "Limits", th: "ข้อจำกัด" },
    sources: { en: "Sources and licences", th: "แหล่งข้อมูลและสัญญาอนุญาต" },
  };
  return `${pick(names[list], language)} (${count})`;
}

/** "Data r4 · built 3 Oct 2026 · sources 3–19 Sep 2024": the revision, its build date and the span of its sources, already formatted. */
export function commandDataLine(revision: string, built: string, span: string, language: Language): string {
  return language === "th" ? `ข้อมูลชุด ${revision} · จัดทำเมื่อ ${built} · แหล่งข้อมูลช่วง ${span}` : `Data ${revision} · built ${built} · sources ${span}`;
}

/** The four "what it is not" sentences in reading order. */
export const COMMAND_DRAWER_NOT: readonly (keyof typeof COMMAND_DRAWER)[] = ["notRealTime", "notWarning", "notOperational", "notScored"];

/** A copy entry in the page language. */
export const commandText = pick;
