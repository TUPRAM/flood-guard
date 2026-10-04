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

// --- The shell: navigation, tools, time bar, legend, notices and help -------------------------------------

/** The situation card (clock and figures) beyond the figures themselves, and the card reserved under it. */
export const COMMAND_SITUATION = {
  label: { en: "Situation at the replay hour", th: "สถานการณ์ ณ ชั่วโมงของการย้อนดู" },
  /** The model-limit chip of the Receding and Mostly receded phases; the full sentence is `COMMAND_FIGURES.modelLimit`. */
  modelLimitShort: { en: "Model limit: standing water and mud are not reconstructed", th: "ข้อจำกัดของแบบจำลอง: ไม่ได้จำลองน้ำท่วมขังและโคลน" },
  exerciseSlot: { en: "exercise items", th: "รายการฝึกซ้อม" },
  tableTitle: { en: "Subdistrict table", th: "ตารางรายตำบล" },
  tableSoon: { en: "The table of the eight subdistricts is not built yet", th: "ยังไม่ได้จัดทำตารางของ 8 ตำบล" },
  loading: { en: "Loading the replay data", th: "กำลังโหลดข้อมูลการย้อนดู" },
  error: { en: "The replay data could not be loaded", th: "โหลดข้อมูลการย้อนดูไม่สำเร็จ" },
  retry: { en: "Try again", th: "ลองอีกครั้ง" },
} as const satisfies Record<string, Localized>;

/** The collapsed situation line of focus mode: "~7,100 lost access · ~16,100 in water". */
export function commandFocusFigures(figures: Pick<CommandFigures, "lostAccess" | "inWater">, language: Language): string {
  return `${roundModelFigure(figures.lostAccess).text} ${pick(COMMAND_FIGURES.changeLost, language)} · ${roundModelFigure(figures.inWater).text} ${pick(COMMAND_FIGURES.changeWater, language)}`;
}

/** "Peak · stage 3.5 m": the phase line of a narrow card. */
export function commandPhaseShortLine(phaseLabel: Localized, stage: number, language: Language): string {
  return `${pick(phaseLabel, language)} · ${language === "th" ? "ระดับสมมุติ" : "assumed stage"} ${commandStageText(stage, language)}`;
}

export const COMMAND_NAV = {
  label: { en: "Sections of the site", th: "ส่วนต่าง ๆ ของเว็บไซต์" },
  public: { en: "Public", th: "ประชาชน" },
  command: { en: "Command (exercise)", th: "ฝึกซ้อมสั่งการ" },
  studio: { en: "Studio", th: "สตูดิโอ" },
  studioHint: { en: "Open the Studio replay at this replay hour", th: "เปิดหน้าย้อนดูในสตูดิโอที่ชั่วโมงเดียวกันนี้" },
  switchLanguage: { en: "Switch to Thai", th: "เปลี่ยนเป็นภาษาอังกฤษ" },
  help: { en: "Help and keys", th: "วิธีใช้และปุ่มลัด" },
  menu: { en: "Menu", th: "เมนู" },
  skip: { en: "Skip to the replay controls", th: "ข้ามไปยังตัวควบคุมการย้อนดู" },
} as const satisfies Record<string, Localized>;

export const COMMAND_TOOLS = {
  label: { en: "Map tools", th: "เครื่องมือแผนที่" },
  view: { en: "Map view", th: "มุมมองแผนที่" },
  viewTitle: { en: "What the map shows", th: "สิ่งที่แสดงบนแผนที่" },
  rescue: { en: "Rescue view", th: "มุมมองกู้ภัย" },
  rescueNote: { en: "Modelled water, roads, reported shelters and the command centre", th: "น้ำตามแบบจำลอง ถนน ที่พักพิงตามรายงาน และศูนย์บัญชาการ" },
  evidence: { en: "Evidence view", th: "มุมมองหลักฐาน" },
  evidenceNote: { en: "Not built yet: candidate sites, satellite images and the season envelope", th: "ยังไม่ได้จัดทำ: สถานที่ที่เป็นไปได้ ภาพถ่ายดาวเทียม และขอบเขตน้ำตลอดฤดู" },
  facilities: { en: "Key facilities", th: "สถานที่สำคัญ" },
  facilitiesNote: { en: "Schools, health, emergency service and community sites from OpenStreetMap", th: "โรงเรียน สถานพยาบาล หน่วยบริการฉุกเฉิน และสถานที่ชุมชน จาก OpenStreetMap" },
  basemap: { en: "Basemap", th: "แผนที่ฐาน" },
  basemapStreet: { en: "Grey street map", th: "แผนที่ถนนสีเทา" },
  basemapTerrain: { en: "Terrain shading", th: "ภูมิประเทศแบบแสงเงา" },
  zoomIn: { en: "Zoom in", th: "ขยายแผนที่" },
  zoomOut: { en: "Zoom out", th: "ย่อแผนที่" },
  fitTown: { en: "Show the town", th: "แสดงเขตเมืองแม่สาย" },
  fitDistrict: { en: "Show the whole district", th: "แสดงทั้งอำเภอ" },
  find: { en: "Find a place (not built yet)", th: "ค้นหาสถานที่ (ยังไม่ได้จัดทำ)" },
  focusOn: { en: "Focus mode: more map, smaller panels", th: "โหมดเน้นแผนที่: ย่อแผงข้อมูลให้เห็นแผนที่มากขึ้น" },
  focusOff: { en: "Leave focus mode", th: "ออกจากโหมดเน้นแผนที่" },
  close: { en: "Close", th: "ปิด" },
} as const satisfies Record<string, Localized>;

export const COMMAND_TIMEBAR = {
  label: { en: "Replay time controls", th: "ตัวควบคุมเวลาในการย้อนดู" },
  play: { en: "Play", th: "เล่น" },
  pause: { en: "Pause", th: "หยุดชั่วคราว" },
  playAgain: { en: "Play again from the first hour", th: "เล่นใหม่ตั้งแต่ชั่วโมงแรก" },
  previousEvent: { en: "Previous event", th: "เหตุการณ์ก่อนหน้า" },
  nextEvent: { en: "Next event", th: "เหตุการณ์ถัดไป" },
  back: { en: "Back one hour", th: "ย้อนกลับ 1 ชั่วโมง" },
  forward: { en: "Forward one hour", th: "ไปข้างหน้า 1 ชั่วโมง" },
  backShort: { en: "−1 h", th: "−1 ชม." },
  forwardShort: { en: "+1 h", th: "+1 ชม." },
  speed: { en: "Playback speed", th: "ความเร็วในการเล่น" },
  days: { en: "Go to a day of September 2024", th: "ไปยังวันที่ในเดือนกันยายน 2567 (2024)" },
  slider: { en: "Replay hour", th: "ชั่วโมงของการย้อนดู" },
  notYetKnown: { en: "not yet known at this hour", th: "ยังไม่ทราบ ณ ชั่วโมงนี้" },
  phases: { en: "Phases of the event", th: "ระยะของเหตุการณ์" },
  rain: { en: "Rain per hour at two gauges (observed)", th: "ฝนรายชั่วโมงที่สถานีวัดฝน 2 แห่ง (ข้อมูลตรวจวัด)" },
  rainShort: { en: "Rain mm/h · observed", th: "ฝน มม./ชม. · ตรวจวัด" },
} as const satisfies Record<string, Localized>;

/** Short label and full meaning of each playback speed. */
export const COMMAND_SPEED_COPY: Readonly<Record<"hour_per_second" | "four_per_second" | "drill", { short: Localized; meaning: Localized }>> = {
  hour_per_second: {
    short: { en: "1 h/s", th: "1 ชม./วิ" },
    meaning: { en: "1 replay hour per second", th: "1 ชั่วโมงของการย้อนดูต่อ 1 วินาที" },
  },
  four_per_second: {
    short: { en: "4 h/s", th: "4 ชม./วิ" },
    meaning: { en: "4 replay hours per second", th: "4 ชั่วโมงของการย้อนดูต่อ 1 วินาที" },
  },
  drill: {
    short: { en: "Drill", th: "ฝึกซ้อม" },
    meaning: { en: "Drill speed: 1 replay hour per minute", th: "ความเร็วฝึกซ้อม: 1 ชั่วโมงของการย้อนดูต่อ 1 นาที" },
  },
};

/** Phase names short enough for a narrow band; the manifest's own label is used where there is room. */
export const COMMAND_PHASE_SHORT: Readonly<Record<string, Localized>> = {
  dry: { en: "Dry", th: "ปกติ" },
  onset: { en: "Onset", th: "เริ่มท่วม" },
  peak: { en: "Peak", th: "สูงสุด" },
  receding: { en: "Receding", th: "น้ำลด" },
  gone: { en: "Mostly receded", th: "ลดเกือบหมด" },
};

/** "Go to 12 Sep" / "ไปยังวันที่ 12 ก.ย.": the name of a day chip. */
export function commandDayLabel(date: string, language: Language): string {
  return language === "th" ? `ไปยังวันที่ ${formatShortDate(date, language)}` : `Go to ${formatShortDate(date, language)}`;
}

/** What the slider says to a screen reader: "12 Sep 2024 · 12:00 ICT, hour 84 of 264". */
export function commandSliderText(hour: number, language: Language): string {
  return `${commandMoment(hour, language)}, ${commandHourOf(hour, language)}`;
}

export const COMMAND_LEGEND = {
  chip: { en: "Legend", th: "สัญลักษณ์" },
  title: { en: "Legend", th: "คำอธิบายสัญลักษณ์" },
  close: { en: "Close the legend", th: "ปิดคำอธิบายสัญลักษณ์" },
  water: { en: "Modelled water", th: "น้ำตามแบบจำลอง" },
  shallow: { en: "under 0.3 m", th: "ลึกไม่ถึง 0.3 เมตร" },
  deep: { en: "0.3 m or more", th: "ลึก 0.3 เมตรขึ้นไป" },
  lowConfidence: { en: "lowest confidence", th: "ความเชื่อมั่นต่ำที่สุด" },
  veil: { en: "outside the district", th: "นอกเขตอำเภอ" },
  roads: { en: "Roads (model)", th: "ถนน (แบบจำลอง)" },
  roadDry: { en: "dry", th: "แห้ง" },
  roadWet: { en: "wet, under 0.3 m", th: "มีน้ำ ไม่ถึง 0.3 เมตร" },
  roadImpassable: { en: "impassable", th: "สัญจรไม่ได้" },
  roadUnmodelled: { en: "not modelled", th: "ไม่ได้จำลอง" },
  places: { en: "Places", th: "สถานที่" },
  shelter: { en: "shelter reported in 2024", th: "ที่พักพิงตามรายงานปี 2567 (2024)" },
  shelterWet: { en: "shelter, wet in the model", th: "ที่พักพิงที่มีน้ำตามแบบจำลอง" },
  commandCentre: { en: "command centre (reported)", th: "ศูนย์บัญชาการ (ตามรายงาน)" },
  facility: { en: "key facility", th: "สถานที่สำคัญ" },
  facilityWet: { en: "facility in modelled water", th: "สถานที่สำคัญในน้ำตามแบบจำลอง" },
  boundary: { en: "subdistrict boundary", th: "เขตตำบล" },
  note: { en: "Model, low confidence. Bridge decks and the current are not modelled.", th: "แบบจำลอง ความเชื่อมั่นต่ำ ไม่ได้จำลองพื้นสะพานและกระแสน้ำ" },
} as const satisfies Record<string, Localized>;

export const COMMAND_MAP = {
  label: { en: "Map of Mae Sai district at the replay hour", th: "แผนที่อำเภอแม่สาย ณ ชั่วโมงของการย้อนดู" },
  outside: { en: "outside the district · not modelled", th: "นอกเขตอำเภอ · ไม่ได้จำลอง" },
  waterError: {
    en: "The water layer could not be loaded. The figures and the roads still follow the replay hour.",
    th: "โหลดชั้นข้อมูลน้ำไม่สำเร็จ ตัวเลขและถนนยังเปลี่ยนตามชั่วโมงของการย้อนดู",
  },
  basemapFallback: { en: "Street map unavailable: showing terrain shading", th: "โหลดแผนที่ถนนไม่ได้ จึงแสดงภูมิประเทศแบบแสงเงาแทน" },
  credits: { en: "Map credits and scale", th: "ที่มาของแผนที่และมาตราส่วน" },
  shelter: { en: "Shelter reported in use in 2024", th: "ที่พักพิงที่มีรายงานว่าใช้ในปี 2567 (2024)" },
  commandCentre: { en: "District incident command centre in 2024, not a shelter", th: "ศูนย์บัญชาการเหตุการณ์อำเภอ ปี 2567 (2024) ไม่ใช่ที่พักพิง" },
  reported: { en: "Reported, not surveyed", th: "ตามรายงาน ไม่ได้สำรวจ" },
  dryNow: { en: "Dry in the model at this replay hour", th: "แห้งตามแบบจำลอง ณ ชั่วโมงนี้ของการย้อนดู" },
  wetNow: { en: "In modelled water at this replay hour", th: "อยู่ในน้ำตามแบบจำลอง ณ ชั่วโมงนี้ของการย้อนดู" },
  notModelled: { en: "Outside the modelled area", th: "อยู่นอกพื้นที่ที่แบบจำลองครอบคลุม" },
  counted: { en: "Counted in the access figures", th: "นับรวมในตัวเลขการเข้าถึง" },
  notCounted: { en: "Not counted in the access figures", th: "ไม่นับรวมในตัวเลขการเข้าถึง" },
  firstUse: { en: "First reported use", th: "รายงานการใช้ครั้งแรก" },
  occupancy: { en: "Occupancy as reported", th: "จำนวนผู้พักพิงตามรายงาน" },
  notReported: { en: "not reported", th: "ไม่มีรายงาน" },
  select: { en: "Select for details", th: "เลือกเพื่อดูรายละเอียด" },
  unnamed: { en: "Unnamed", th: "ไม่มีชื่อ" },
} as const satisfies Record<string, Localized>;

/** Credits printed on the map itself; the full list is in the information drawer. */
export const COMMAND_CREDITS = { osm: "© OpenStreetMap contributors", terrain: "Copernicus DEM © DLR, Airbus DS" } as const;

/** Types of the key facilities (OpenStreetMap). */
export const COMMAND_FACILITY_TYPES: Readonly<Record<string, Localized>> = {
  shelter_candidate: { en: "Possible shelter site", th: "จุดพักพิงที่เป็นไปได้" },
  school: { en: "School", th: "โรงเรียน" },
  emergency_service: { en: "Emergency service", th: "หน่วยบริการฉุกเฉิน" },
  community_facility: { en: "Community facility", th: "สถานที่ชุมชน" },
  healthcare: { en: "Healthcare", th: "สถานพยาบาล" },
};
export const commandFacilityType = (type: string, language: Language): string => {
  const known = COMMAND_FACILITY_TYPES[type];
  return known ? pick(known, language) : type;
};

/** "1 km" / "500 m" / "1 กม.": the length under the scale bar. */
export function commandScaleLabel(metres: number, language: Language): string {
  if (metres >= 1000) return `${metres / 1000} ${language === "th" ? "กม." : "km"}`;
  return `${metres} ${language === "th" ? "ม." : "m"}`;
}

/**
 * The span of the sources as the replay data dates it ("2024-09-03T23:16:00Z/2024-09-19T17:00:00Z" reads
 * "3–19 Sep 2024"); the text itself when it is not such a span.
 */
export function commandSourceSpan(sourceTimestamp: string, language: Language): string {
  const [start, end] = sourceTimestamp.split("/").map((part) => part.slice(0, 10));
  if (!start || !end || !/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end)) return sourceTimestamp;
  const year = Number(end.slice(0, 4));
  const yearText = language === "th" ? `${year + 543} (${year})` : String(year);
  if (start.slice(0, 7) === end.slice(0, 7)) {
    const [, ...month] = formatShortDate(end, language).split(" ");
    return `${Number(start.slice(8))}–${Number(end.slice(8))} ${month.join(" ")} ${yearText}`;
  }
  return `${formatShortDate(start, language)} – ${formatShortDate(end, language)} ${yearText}`;
}

export const COMMAND_HELP = {
  title: { en: "Help and keys", th: "วิธีใช้และปุ่มลัด" },
  intro: {
    en: "This page replays the September 2024 flood for exercises. Press play, or step through the hours: the figures and the map follow the replay hour.",
    th: "หน้านี้ย้อนดูเหตุการณ์น้ำท่วมเดือนกันยายน 2567 (2024) เพื่อการฝึกซ้อม กดเล่นหรือเลื่อนทีละชั่วโมง ตัวเลขและแผนที่จะเปลี่ยนตามชั่วโมงของการย้อนดู",
  },
  keys: { en: "Keys", th: "ปุ่มลัด" },
  keySpace: { en: "Play or pause", th: "เล่นหรือหยุดชั่วคราว" },
  keyArrows: { en: "One replay hour back or forward", th: "ย้อนกลับหรือไปข้างหน้า 1 ชั่วโมง" },
  keyShiftArrows: { en: "One day back or forward", th: "ย้อนกลับหรือไปข้างหน้า 1 วัน" },
  keyBrackets: { en: "Previous or next event", th: "เหตุการณ์ก่อนหน้าหรือถัดไป" },
  keyFocus: { en: "Focus mode on or off", th: "เปิดหรือปิดโหมดเน้นแผนที่" },
  keyHelp: { en: "This help", th: "หน้าวิธีใช้นี้" },
  keyEscape: { en: "Close what is open", th: "ปิดสิ่งที่เปิดอยู่" },
  hotlines: {
    en: "In a real emergency call 1784 (disaster), 1669 (medical emergency) or 191 (police). This page does not reach them.",
    th: "หากเกิดเหตุฉุกเฉินจริง โทร 1784 (สาธารณภัย) 1669 (การแพทย์ฉุกเฉิน) หรือ 191 (ตำรวจ) หน้านี้ไม่ได้เชื่อมต่อกับหน่วยงานดังกล่าว",
  },
  more: { en: "About this exercise", th: "เกี่ยวกับการฝึกซ้อมนี้" },
} as const satisfies Record<string, Localized>;

/** The keys of the help sheet in reading order: the keycaps as printed, and the entry that says what they do. */
export const COMMAND_HELP_KEYS: readonly { keys: readonly string[]; text: keyof typeof COMMAND_HELP }[] = [
  { keys: ["Space"], text: "keySpace" },
  { keys: ["←", "→"], text: "keyArrows" },
  { keys: ["Shift", "←", "→"], text: "keyShiftArrows" },
  { keys: ["[", "]"], text: "keyBrackets" },
  { keys: ["F"], text: "keyFocus" },
  { keys: ["?"], text: "keyHelp" },
  { keys: ["Esc"], text: "keyEscape" },
];

/** Further labels of the information drawer. */
export const COMMAND_DRAWER_SOURCES = {
  licence: { en: "Licence", th: "สัญญาอนุญาต" },
  dated: { en: "Dated", th: "วันที่ของข้อมูล" },
  showAll: { en: "Show all", th: "แสดงทั้งหมด" },
} as const satisfies Record<string, Localized>;
