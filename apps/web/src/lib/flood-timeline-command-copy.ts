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
  notWarning: { en: "not an official warning", th: "ไม่ใช่คำเตือนอย่างเป็นทางการ" },
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
  stage: { en: "assumed stage", th: "ระดับแม่น้ำสมมุติ" },
  stageNote: { en: "illustrative", th: "ค่าเพื่อการอธิบาย" },
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

/** The clock hour of a replay hour on its own: "11:00" / "11:00 น." (the hour the "what changed" line compares with). */
export function commandHourClock(hour: number, language: Language): string {
  const { time } = replayClock(hour);
  return language === "th" ? `${time} น.` : time;
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

/**
 * "Phase: Peak · assumed stage 3.5 m (illustrative)"; `phaseLabel` is the manifest's own label. The line is one line
 * at every replay hour (the longest reads "Phase: Mostly receded · assumed stage <0.1 m (illustrative)"), so the card
 * never changes height while the replay plays. The sentence behind it is `COMMAND_CLOCK.stageMeaning`.
 */
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
  /** The standing limit of the water layer, shown before the river falls: the replay data models depth only. */
  modelCurrent: {
    en: "The model gives water depth only. The speed of the current, debris and mud are not modelled.",
    th: "แบบจำลองให้เฉพาะความลึกของน้ำ ไม่ได้จำลองความเร็วของกระแสน้ำ เศษซากที่ไหลมากับน้ำ และโคลน",
  },
  /** Shown in the Receding and Mostly receded phases. */
  modelLimit: {
    en: "The model dries as the river falls; standing water and mud are not reconstructed.",
    th: "ในแบบจำลอง น้ำจะแห้งทันทีที่ระดับแม่น้ำลดลง จึงไม่ได้จำลองน้ำท่วมขังและโคลนที่ค้างอยู่",
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
  /** The rounded value without its unit: "~7,100", "<10", "0", "~164". */
  value: string;
  /** The unit printed small after the value ("km" / "กม."); null for a count of residents. */
  unit: string | null;
  caption: string;
  /** The caption of a narrow card, one line: "lost access", "in water", "roads impassable". */
  captionShort: string;
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
      unit: null,
      caption: pick(COMMAND_FIGURES.lostAccess, language),
      captionShort: pick(COMMAND_FIGURES.changeLost, language),
      sub: commandBaseText(figures.withinReachBefore, language, true),
      meaning: `${pick(COMMAND_FIGURES.lostAccessMeaning, language)} ${pick(COMMAND_FIGURES.scope, language)}`,
    },
    {
      id: "inWater",
      value: roundModelFigure(figures.inWater).text,
      unit: null,
      caption: pick(COMMAND_FIGURES.inWater, language),
      captionShort: pick(COMMAND_FIGURES.changeWater, language),
      sub: null,
      meaning: pick(COMMAND_FIGURES.inWaterMeaning, language),
    },
    {
      id: "roads",
      value: roundModelKm(figures.roadKmImpassable).text,
      unit: km(language),
      caption: pick(COMMAND_FIGURES.roads, language),
      captionShort: pick(COMMAND_FIGURES.roads, language),
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
  /** "Since 11:00" or the first-hour sentence. */
  lead: string;
  /** "+100 lost access", "0 in water", "+1 km impassable"; empty when nothing moved. */
  figures: string[];
  /** The first line of the card: the lead with the three differences, or with "no change". It is never cut. */
  summary: string;
  /** Named roads impassable for the first time as a whole road; null when there is none. */
  roadsCut: string | null;
  /** Named roads passable again in the model as a whole road; null when there is none. */
  roadsOpen: string | null;
  /** Both road lists as one text; null when there is none. */
  roads: string | null;
  text: string;
}

/** A line of road names is kept to about this many letters, so it fits one line of the card. */
const ROAD_LINE_CHARS = 68;

/**
 * How many letters wide a text is, roughly: Thai vowels and tone marks that stand above or below a consonant take no
 * width of their own, so they are not counted.
 */
export function commandTextWidth(text: string): number {
  return text.replace(/[\u0E31\u0E34-\u0E3A\u0E47-\u0E4E]/g, "").length;
}

/** The longest list of road names that fits one line of the card: up to `limit` names, then "and n more". */
function fittedRoadLine(label: string, roads: readonly Pick<CommandRoadChange, "name">[], language: Language, limit: number): string {
  for (let shown = Math.max(1, limit); shown > 1; shown -= 1) {
    const line = `${label}: ${commandRoadList(roads, language, shown)}`;
    if (commandTextWidth(line) <= ROAD_LINE_CHARS) return line;
  }
  return `${label}: ${commandRoadList(roads, language, 1)}`;
}

/**
 * What changed since the hour before, as the situation card says it. `sinceText` is the hour compared with, already
 * formatted (e.g. `commandHourClock(change.sinceHour, language)`). A difference is rounded like its figure and printed
 * with its sign and no tilde ("+100", "−<10", "0"): the rounding rule is stated once, in the information drawer. Only
 * roads newly impassable as a whole road (or passable again as a whole) are named.
 */
export function commandChangeLine(change: CommandChange, sinceText: string, language: Language, roadLimit = 2): CommandChangeLine {
  if (change.sinceHour === null) {
    const lead = pick(COMMAND_FIGURES.firstHour, language);
    return { lead, figures: [], summary: lead, roadsCut: null, roadsOpen: null, roads: null, text: lead };
  }
  const lead = language === "th" ? `ตั้งแต่ ${sinceText}` : `Since ${sinceText}`;
  const plain = (text: string): string => text.replace("~", "");
  const lost = roundModelChange(change.lostAccess);
  const water = roundModelChange(change.inWater);
  const roadKm = roundModelChange(change.roadKmImpassable, roundModelKm);
  const moved = lost.direction !== 0 || water.direction !== 0 || roadKm.direction !== 0;
  const figures = moved
    ? [
        `${plain(lost.text)} ${pick(COMMAND_FIGURES.changeLost, language)}`,
        `${plain(water.text)} ${pick(COMMAND_FIGURES.changeWater, language)}`,
        `${plain(roadKm.text)} ${pick(COMMAND_FIGURES.changeRoads, language)}`,
      ]
    : [];
  const cut = change.newlyImpassable.named.filter((road) => road.whole);
  const open = change.passableAgain.named.filter((road) => road.whole);
  const roadsCut = cut.length > 0 ? fittedRoadLine(language === "th" ? "ถนนที่เริ่มสัญจรไม่ได้" : "newly impassable", cut, language, roadLimit) : null;
  const roadsOpen = open.length > 0 ? fittedRoadLine(language === "th" ? "ถนนที่กลับมาสัญจรได้ในแบบจำลอง" : "passable again in the model", open, language, roadLimit) : null;
  const roads = roadsCut && roadsOpen ? `${roadsCut} · ${roadsOpen}` : roadsCut ?? roadsOpen;
  const summary = `${lead}: ${moved ? figures.join(" · ") : pick(COMMAND_FIGURES.noChange, language)}`;
  return { lead, figures, summary, roadsCut, roadsOpen, roads, text: `${summary}${roads ? ` · ${roads}` : ""}` };
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
    tag: { en: "Observed", th: "ข้อมูลที่สังเกตได้" },
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
    th: "ไม่ใช่คำเตือนอย่างเป็นทางการ และไม่ใช่ระบบสั่งการ FloodGuard ไม่รับสายแจ้งเหตุและไม่ส่งข้อมูลถึงหน่วยกู้ภัย สายด่วน 1784 (สาธารณภัย) 1669 (การแพทย์ฉุกเฉิน) และ 191 (ตำรวจ) ยังคงเป็นช่องทางแจ้งเหตุของทางราชการ",
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
    en: "Modelled figures are rounded: a tilde, then the nearest 10 below 1,000 and the nearest 100 above. A difference against the hour before is rounded the same way and printed with its sign and no tilde. Counted things, such as exercise items, are plain numbers.",
    th: "ตัวเลขจากแบบจำลองปัดเศษแล้ว: มีเครื่องหมาย ~ นำหน้า ปัดเป็นหลักสิบ (10) เมื่อต่ำกว่า 1,000 และเป็นหลักร้อย (100) เมื่อสูงกว่านั้น ผลต่างเทียบกับชั่วโมงก่อนหน้าปัดเศษแบบเดียวกัน แสดงพร้อมเครื่องหมายบวกหรือลบ และไม่มีเครื่องหมาย ~ ส่วนสิ่งที่นับได้จริง เช่น รายการฝึกซ้อม แสดงเป็นตัวเลขตรงตัว",
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

/**
 * Sentences as one text. English sets a full stop after each; Thai sentences take no full stop and are set apart by a
 * space, as Thai is written.
 */
export function commandSentences(parts: readonly string[], language: Language): string {
  if (language === "th") return parts.join(" ");
  return parts.map((part) => (/[.!?]$/.test(part) ? part : `${part}.`)).join(" ");
}

/**
 * A share as the page prints it: "83%". A share just under the whole reads ">99%" and one just over nothing "<1%", so
 * a rounded percentage never contradicts the count beside it.
 */
export function commandPercent(share: number): string {
  const percent = Math.round(share * 100);
  if (percent >= 100 && share < 1) return ">99%";
  if (percent <= 0 && share > 0) return "<1%";
  return `${percent}%`;
}

/** The share in brackets after a count: " (83%)". It is left out when the share is unknown or its base is under ten residents. */
export function commandShareNote(share: number | null, base: number): string {
  if (share === null || !Number.isFinite(share) || !(base >= 10)) return "";
  return ` (${commandPercent(share)})`;
}

// --- The shell: navigation, tools, time bar, legend, notices and help -------------------------------------

/** The situation card (clock and figures) beyond the figures themselves. */
export const COMMAND_SITUATION = {
  label: { en: "Situation at the replay hour", th: "สถานการณ์ ณ ชั่วโมงของการย้อนดู" },
  /** The model-limit chip of the Receding and Mostly receded phases; the full sentence is `COMMAND_FIGURES.modelLimit`. */
  modelLimitShort: { en: "Model limit: standing water and mud not modelled", th: "ข้อจำกัดของแบบจำลอง: ไม่ได้จำลองน้ำท่วมขังและโคลน" },
  /** The model-limit chip of the hours before the river falls; the full sentence is `COMMAND_FIGURES.modelCurrent`. */
  modelCurrentShort: { en: "Model limit: the current is not modelled", th: "ข้อจำกัดของแบบจำลอง: ไม่ได้จำลองกระแสน้ำ" },
  exerciseSlot: { en: "exercise items", th: "รายการฝึกซ้อม" },
  /** Below 900 px the page keeps the banner, this card, the map and the time dock, and says what is left out. */
  narrow: {
    en: "Narrow window: the subdistrict table and the map tools need a window at least 900 px wide.",
    th: "หน้าต่างแคบ: ตารางรายตำบลและเครื่องมือแผนที่ต้องใช้หน้าต่างกว้างอย่างน้อย 900 พิกเซล",
  },
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
  rescueNote: { en: "Modelled water, roads, reported shelters, the command centre and the reports", th: "น้ำตามแบบจำลอง ถนน ที่พักพิงตามรายงาน ศูนย์บัญชาการ และรายงานต่าง ๆ" },
  evidence: { en: "Evidence view", th: "มุมมองหลักฐาน" },
  evidenceNote: {
    en: "Not built yet: candidate sites and satellite images. The 2024 season envelope is drawn in hindsight mode.",
    th: "ยังไม่ได้จัดทำ: สถานที่ที่อาจใช้เป็นที่พักพิงและภาพถ่ายดาวเทียม ส่วนขอบเขตน้ำตลอดฤดูปี 2567 (2024) แสดงในโหมดมองย้อนหลัง",
  },
  facilities: { en: "Key facilities", th: "สถานที่สำคัญ" },
  facilitiesNote: { en: "Schools, health, emergency service and community sites from OpenStreetMap", th: "โรงเรียน สถานพยาบาล หน่วยบริการฉุกเฉิน และสถานที่ชุมชน จาก OpenStreetMap" },
  basemap: { en: "Basemap", th: "แผนที่ฐาน" },
  basemapStreet: { en: "Grey street map", th: "แผนที่ถนนสีเทา" },
  basemapTerrain: { en: "Terrain shading", th: "ภูมิประเทศแบบแสงเงา" },
  zoomIn: { en: "Zoom in", th: "ขยายแผนที่" },
  zoomOut: { en: "Zoom out", th: "ย่อแผนที่" },
  fitTown: { en: "Show the town", th: "แสดงเขตเมืองแม่สาย" },
  fitDistrict: { en: "Show the whole district", th: "แสดงทั้งอำเภอ" },
  find: { en: "Find a place", th: "ค้นหาสถานที่" },
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
    short: { en: "Drill", th: "1 ชม./นาที" },
    meaning: { en: "Drill speed: 1 replay hour per minute", th: "ความเร็วสำหรับฝึกปฏิบัติ: 1 ชั่วโมงของการย้อนดูต่อ 1 นาที" },
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
  shelterWet: { en: "shelter, wet in the model", th: "ที่พักพิงที่น้ำท่วมถึงตามแบบจำลอง" },
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

/**
 * "6 shelters reported in use in 2024 stand close together here.": the count mark of the district zoom. `centre` adds
 * the district command centre, whose diamond the mark then shows beside the star.
 */
export function commandSiteGroupTitle(count: number, centre: boolean, language: Language): string {
  if (language === "th") {
    return `ที่พักพิงที่มีรายงานว่าใช้ในปี 2567 (2024) จำนวน ${count} แห่ง${centre ? " และศูนย์บัญชาการเหตุการณ์อำเภอ " : ""}อยู่ใกล้กันในบริเวณนี้`;
  }
  return `${count} shelters reported in use in 2024${centre ? " and the district command centre" : ""} stand close together here.`;
}

/** Credits printed on the map itself; the full list is in the information drawer. */
export const COMMAND_CREDITS = { osm: "© OpenStreetMap contributors", terrain: "Copernicus DEM © DLR, Airbus DS" } as const;

/** Types of the key facilities (OpenStreetMap). */
export const COMMAND_FACILITY_TYPES: Readonly<Record<string, Localized>> = {
  shelter_candidate: { en: "Possible shelter site", th: "สถานที่ที่อาจใช้เป็นที่พักพิง" },
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
  keyEscape: { en: "Close what is open, or clear the selection", th: "ปิดสิ่งที่เปิดอยู่ หรือยกเลิกการเลือก" },
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

/** "data r4" / "ข้อมูลชุด r4": the revision of the replay data, in the map credits. */
export function commandDataTag(revision: string, language: Language): string {
  return language === "th" ? `ข้อมูลชุด ${revision}` : `data ${revision}`;
}

// --- The subdistrict table (region B2) -------------------------------------------------------------------

/**
 * The table of the eight subdistricts. Its left column group is a model count of this replay hour and holds no rating
 * of any kind (decision D7); its right column group is the planning class of the signed protocol, fixed in time.
 */
export const COMMAND_TABLE = {
  title: { en: "Subdistrict table", th: "ตารางรายตำบล" },
  loading: { en: "The table appears when the replay data has loaded", th: "ตารางจะแสดงเมื่อโหลดข้อมูลการย้อนดูเสร็จ" },
  groupHour: { en: "This hour · model", th: "ชั่วโมงนี้ · แบบจำลอง" },
  groupHourTag: { en: "low confidence", th: "ความเชื่อมั่นต่ำ" },
  groupPlan: { en: "Plan · fixed", th: "แผน · คงที่" },
  groupPlanMeaning: { en: "Fixed in time: it does not follow the replay hour", th: "คงที่ ไม่เปลี่ยนตามชั่วโมงของการย้อนดู" },
  colPosition: { en: "Order in this hour", th: "ลำดับในชั่วโมงนี้" },
  colTambon: { en: "subdistrict", th: "ตำบล" },
  colLost: { en: "lost access", th: "สูญเสียการเข้าถึง" },
  colWater: { en: "in water", th: "ในน้ำ" },
  colPlanPosition: { en: "Planning position", th: "อันดับตามแผน" },
  /** The mark on a row where most residents had no shelter of the set in reach before the flood. */
  noReachMeaning: {
    en: "Most residents here had no shelter of the set within a 2 km walk even before the flood, so they can never count as having lost access.",
    th: "ผู้อยู่อาศัยส่วนใหญ่ในตำบลนี้ไม่มีที่พักพิงของชุดนี้ในระยะเดิน 2 กม. ตั้งแต่ก่อนน้ำท่วม จึงไม่นับเป็นผู้สูญเสียการเข้าถึง",
  },
  planLine: {
    en: "Planning class from the signed protocol. Fixed in time. Not computed from this replay hour.",
    th: "ระดับการดำเนินการ (A–E) มาจากหลักเกณฑ์ที่ลงนามแล้ว คงที่ไม่เปลี่ยนตามเวลา และไม่ได้คำนวณจากชั่วโมงนี้ของการย้อนดู",
  },
  /** The short form under the table, one line; the full sentence (`planLine`) is in the inspector and on hover. */
  planLineShort: { en: "Fixed in time; not computed from this hour", th: "คงที่ไม่เปลี่ยนตามเวลา ไม่ได้คำนวณจากชั่วโมงนี้" },
  notIssued: { en: "Not issued yet", th: "ยังไม่มีผลการจัดระดับ" },
  notIssuedTask: { en: "Not issued yet (task E8)", th: "ยังไม่มีผลการจัดระดับ (งาน E8)" },
  eNeverSafe: { en: "Class E never means safe", th: "ระดับ E ไม่ได้หมายความว่าปลอดภัย" },
  noClass: { en: "No class: fewer than 100 residents", th: "ไม่จัดระดับ: ผู้อยู่อาศัยน้อยกว่า 100 คน" },
  stabilityHeld: {
    en: "headline-eligible: the class holds when one component at a time is left out",
    th: "ใช้เป็นผลหลักได้: ระดับคงเดิมเมื่อตัดองค์ประกอบออกทีละตัว",
  },
  stabilityNotEvaluated: { en: "stability not evaluated", th: "ยังไม่ได้ประเมินความเสถียร" },
  stabilityUnstable: { en: "unstable: verify", th: "ไม่เสถียร: ต้องตรวจสอบ" },
  /** The key of the chips, under the table once a class is issued. */
  chipKey: {
    en: "A filled chip is headline-eligible; an outlined chip: stability not evaluated; a question mark: unstable: verify.",
    th: "ป้ายทึบ: ใช้เป็นผลหลักได้ ป้ายโปร่ง: ยังไม่ได้ประเมินความเสถียร เครื่องหมายคำถาม: ไม่เสถียร ต้องตรวจสอบ",
  },
  /** The lane of each case, as the protocol's display rule words it. */
  laneO1: { en: "Own model candidate: verify before action", th: "ผลเบื้องต้นจากแบบจำลองของโครงการเอง: ต้องตรวจสอบก่อนดำเนินการ" },
  laneSE1: { en: "Scenario: what-if (2024 season envelope)", th: "สถานการณ์จำลอง: กรณีสมมุติ (ขอบเขตน้ำตลอดฤดูปี 2567 (2024))" },
  orderBy: { en: "Order rows by", th: "เรียงแถวตาม" },
  orderHour: { en: "This hour", th: "ชั่วโมงนี้" },
  orderPlanning: { en: "Planning", th: "แผน" },
  orderPlanningOff: {
    en: "No planning position has been issued, so the rows cannot be ordered by it yet",
    th: "ยังไม่มีอันดับตามแผน จึงยังเรียงแถวตามแผนไม่ได้",
  },
  positionFrom: { en: "Planning position from", th: "อันดับตามแผนจาก" },
  positionFromMeaning: {
    en: "The planning position comes from one case at a time. The two cases are never averaged or counted together.",
    th: "อันดับตามแผนมาจากกรณีเดียวในแต่ละครั้ง ไม่มีการเฉลี่ยหรือนับสองกรณีรวมกัน",
  },
  shelterSet: { en: "Shelter set", th: "ชุดที่พักพิง" },
  setNote: {
    en: "All residents at road nodes · figures change with the set · no set is graded",
    th: "นับผู้อยู่อาศัยทั้งหมดที่จุดถนน · ตัวเลขเปลี่ยนตามชุดที่เลือก · ไม่ได้ตัดสินชุดใด",
  },
  orderHeld: { en: "Order held", th: "คงลำดับไว้" },
  orderHeldMeaning: {
    en: "The order of the rows is held while the pointer or the keyboard is in the table, or the time thumb is dragged. The numbers still follow the replay hour.",
    th: "คงลำดับแถวไว้ขณะที่ตัวชี้หรือแป้นพิมพ์อยู่ในตาราง หรือขณะลากตัวเลื่อนเวลา ตัวเลขยังเปลี่ยนตามชั่วโมงของการย้อนดู",
  },
  options: { en: "Table options", th: "ตัวเลือกของตาราง" },
  tabQueue: { en: "Subdistricts", th: "ตำบล" },
  tabs: { en: "Left column", th: "แผงด้านซ้าย" },
  sinceBefore: { en: "since the hour before", th: "เทียบกับชั่วโมงก่อนหน้า" },
} as const satisfies Record<string, Localized>;

/** The names of the five planning classes. They appear only beside a class of the signed protocol, never beside a replay hour. */
export const COMMAND_CLASS_NAMES: Readonly<Record<"A" | "B" | "C" | "D" | "E", Localized>> = {
  A: { en: "Protect lives now", th: "ปกป้องชีวิตทันที" },
  B: { en: "Keep routes open", th: "รักษาเส้นทางให้สัญจรได้" },
  C: { en: "Protect essential services", th: "คุ้มครองบริการจำเป็น" },
  D: { en: "Build resilience", th: "สร้างความพร้อมระยะยาว" },
  E: { en: "Monitor and verify", th: "ติดตามและตรวจสอบ" },
};

/** "Class E · Monitor and verify" / "ระดับ E · ติดตามและตรวจสอบ". */
export function commandClassLine(letter: "A" | "B" | "C" | "D" | "E", language: Language): string {
  return `${language === "th" ? "ระดับ" : "Class"} ${letter} · ${pick(COMMAND_CLASS_NAMES[letter], language)}`;
}

/** The short label of a shelter set on its switch, with the number of sites it counts: "2024 · 12" and "Plan · 8". */
export function commandSetLabel(set: "reported" | "plan", sites: number, language: Language): string {
  if (language === "th") return set === "reported" ? `ปี 2567 · ${sites}` : `แผน · ${sites}`;
  return set === "reported" ? `2024 · ${sites}` : `Plan · ${sites}`;
}

/** What a shelter set is, in one sentence. The sites of the plan are candidates to verify. */
export function commandSetMeaning(set: "reported" | "plan", sites: number, language: Language): string {
  if (set === "reported") {
    return language === "th"
      ? `สถานที่ ${sites} แห่งที่ระบุตำแหน่งได้ จากที่พักพิงที่มีรายงานว่าใช้ในปี 2567 (2024)`
      : `The ${sites} located sites among the shelters reported in use in 2024`;
  }
  return language === "th"
    ? `สถานที่ ${sites} แห่งแรกของแผนจัดอันดับ: เป็นสถานที่ที่ควรตรวจสอบ ไม่ใช่รายชื่อที่พักพิงที่ต้องเปิด`
    : `The first ${sites} sites of the ranked plan: candidates to verify, not a list of sites to open`;
}

/** The one-line footer of the "+" mark, for the shelter set the table counts. */
export function commandNoReachNote(set: "reported" | "plan", language: Language): string {
  if (language === "th") {
    return set === "reported"
      ? "+ ผู้อยู่อาศัยส่วนใหญ่ไม่มีที่พักพิงตามรายงานในระยะเดิน 2 กม. ตั้งแต่ก่อนน้ำท่วม"
      : "+ ผู้อยู่อาศัยส่วนใหญ่ไม่มีสถานที่ของแผนในระยะเดิน 2 กม. ตั้งแต่ก่อนน้ำท่วม";
  }
  return set === "reported"
    ? "+ most residents had no reported shelter within 2 km before the flood"
    : "+ most residents had no site of the plan within 2 km before the flood";
}

/** "7 located place records (news, not surveyed)": the count a row carries. */
export function commandRecordCount(count: number, language: Language): string {
  if (language === "th") return `รายการตามสถานที่ที่มีจุดบนแผนที่ ${count} รายการ (จากข่าว ไม่ได้สำรวจ)`;
  return `${count} located place ${count === 1 ? "record" : "records"} (news, not surveyed)`;
}

/** "+~100 since the hour before" / "no change since the hour before": what the change arrow of a row means. */
export function commandRowChange(change: { text: string; direction: -1 | 0 | 1 }, language: Language): string {
  if (change.direction === 0) return language === "th" ? "ไม่เปลี่ยนจากชั่วโมงก่อนหน้า" : "no change since the hour before";
  return `${change.text} ${pick(COMMAND_TABLE.sinceBefore, language)}`;
}

/** "Planning position from SE1" / "อันดับตามแผนจาก SE1". */
export function commandPlanPositionLabel(planningCase: "O1" | "SE1", language: Language): string {
  return `${pick(COMMAND_TABLE.positionFrom, language)} ${planningCase}`;
}

/** The title of a protocol case on its card. */
export function commandCaseTitle(planningCase: "O1" | "SE1", language: Language): string {
  if (planningCase === "O1") {
    return language === "th"
      ? "O1 · พื้นที่ที่อาจมีน้ำท่วมจากการวิเคราะห์ภาพเรดาร์ดาวเทียมของโครงการเอง 16 ก.ย. 2567 (2024)"
      : "O1 · own radar candidates, 16 Sep 2024";
  }
  return language === "th" ? "SE1 · ขอบเขตน้ำตลอดฤดู ส.ค.–ต.ค. 2567 (2024)" : "SE1 · season envelope, Aug–Oct 2024";
}

/** The lane sentence of a case: the protocol's own display wording. */
export function commandCaseLane(planningCase: "O1" | "SE1", language: Language): string {
  return pick(planningCase === "O1" ? COMMAND_TABLE.laneO1 : COMMAND_TABLE.laneSE1, language);
}

/** The stability of a class under guardrail GR8, in a few words. */
export function commandStabilityText(headline: "not_evaluated" | "headline_eligible" | "unstable_verify", language: Language): string {
  return pick(headline === "headline_eligible" ? COMMAND_TABLE.stabilityHeld : headline === "unstable_verify" ? COMMAND_TABLE.stabilityUnstable : COMMAND_TABLE.stabilityNotEvaluated, language);
}

/** What a chip of the plan group says to a screen reader, and on hover. Wherever it names class E it adds that E never means safe. */
export function commandChipLabel(
  planningCase: "O1" | "SE1",
  cell: { letter: "A" | "B" | "C" | "D" | "E" | null; headline: "not_evaluated" | "headline_eligible" | "unstable_verify" } | null,
  language: Language,
): string {
  if (!cell) return `${planningCase}: ${pick(COMMAND_TABLE.notIssued, language)}`;
  if (cell.letter === null) return `${planningCase}: ${pick(COMMAND_TABLE.noClass, language)} · ${commandCaseLane(planningCase, language)}`;
  const never = cell.letter === "E" ? ` · ${pick(COMMAND_TABLE.eNeverSafe, language)}` : "";
  return `${planningCase}: ${commandClassLine(cell.letter, language)}${never} · ${commandCaseLane(planningCase, language)} · ${commandStabilityText(cell.headline, language)}`;
}

// --- The right card (region D): detail and what is known ---------------------------------------------------

export const COMMAND_INSPECTOR = {
  label: { en: "Detail and what is known", th: "รายละเอียดและสิ่งที่ทราบ" },
  tabDetail: { en: "Detail", th: "รายละเอียด" },
  tabKnown: { en: "Known by now", th: "ทราบแล้วถึงชั่วโมงนี้" },
  tabKnownShort: { en: "Known", th: "ทราบแล้ว" },
  close: { en: "Close the card", th: "ปิดแผงนี้" },
  deselect: { en: "Clear the selection", th: "ยกเลิกการเลือก" },
  empty: { en: "Select a subdistrict in the table to see its detail.", th: "เลือกตำบลในตารางเพื่อดูรายละเอียด" },
  knownSoon: {
    en: "The list of what had been reported or observed appears when the replay data has loaded.",
    th: "รายการสิ่งที่มีรายงานหรือสังเกตได้จะแสดงเมื่อโหลดข้อมูลการย้อนดูเสร็จ",
  },
  kind: { en: "Subdistrict", th: "ตำบล" },
  sectionHour: { en: "At this replay hour", th: "ณ ชั่วโมงนี้ของการย้อนดู" },
  facilities: { en: "key facilities in modelled water", th: "สถานที่สำคัญในน้ำตามแบบจำลอง" },
  facilitiesNone: { en: "no key facility mapped here", th: "ไม่มีสถานที่สำคัญในแผนที่ของตำบลนี้" },
  facilitiesWet: { en: "In modelled water", th: "อยู่ในน้ำตามแบบจำลอง" },
  roadsNamed: { en: "Named roads with impassable pieces", th: "ถนนที่มีชื่อซึ่งมีช่วงสัญจรไม่ได้" },
  sectionPeak: { en: "At the modelled peak", th: "ณ ระดับน้ำสูงสุดตามแบบจำลอง" },
  peakSource: {
    en: "From the export table tambon_replay_summary.json. Model, low confidence.",
    th: "จากตารางส่งออก tambon_replay_summary.json แบบจำลอง ความเชื่อมั่นต่ำ",
  },
  peakLoading: { en: "Loading the peak summary", th: "กำลังโหลดสรุป ณ ระดับน้ำสูงสุด" },
  /** Trainee mode, before the replay reaches the hour of the modelled peak. */
  peakLater: {
    en: "Trainee mode: the summary at the modelled peak is shown once the replay reaches that hour.",
    th: "โหมดผู้ฝึก: สรุป ณ ระดับน้ำสูงสุดตามแบบจำลองจะแสดงเมื่อการย้อนดูไปถึงชั่วโมงนั้น",
  },
  peakMissing: { en: "The peak summary of the export pack could not be loaded.", th: "โหลดสรุป ณ ระดับน้ำสูงสุดจากชุดไฟล์ส่งออกไม่สำเร็จ" },
  sectionRecords: { en: "Place records here", th: "รายการตามสถานที่ในตำบลนี้" },
  recordsTag: { en: "Reported in news · not surveyed", th: "ตามรายงานข่าว · ไม่ได้สำรวจ" },
  recordsNone: {
    en: "No located place record in this subdistrict. That is not a sign of little water.",
    th: "ไม่มีรายการตามสถานที่ที่มีจุดบนแผนที่ในตำบลนี้ ซึ่งไม่ได้แปลว่าน้ำน้อย",
  },
  sectionPlan: { en: "Planning class · fixed in time", th: "ระดับการดำเนินการ · คงที่ไม่เปลี่ยนตามเวลา" },
  notIssuedLine: {
    en: "No planning class has been issued for this subdistrict in this case.",
    th: "ยังไม่มีผลการจัดระดับของตำบลนี้ในกรณีนี้",
  },
  action: { en: "Planning action", th: "ข้อเสนอเพื่อการวางแผน" },
  chipKnown: { en: "Known by now", th: "ทราบแล้วถึงชั่วโมงนี้" },
} as const satisfies Record<string, Localized>;

/** "Detail: แม่สาย": the chip that reopens the card on the selected subdistrict. */
export function commandDetailChip(name: string, language: Language): string {
  return `${pick(COMMAND_INSPECTOR.tabDetail, language)}: ${name}`;
}

/** "of 121 km modelled here": the modelled road length of the subdistrict (a length of data, so no tilde). */
export function commandRoadBase(km: number, language: Language): string {
  const whole = Math.round(km).toLocaleString("en-US");
  return language === "th" ? `จากถนนในแบบจำลอง ${whole} กม.` : `of ${whole} km modelled here`;
}

/** "3 of 9": key facilities in modelled water among those the model covers. Counted things keep plain digits. */
export function commandFacilityCount(inWater: number, modelled: number, language: Language): string {
  return language === "th" ? `${inWater} จาก ${modelled} แห่ง` : `${inWater} of ${modelled}`;
}

/**
 * The sentence behind the "+" mark of one subdistrict: how many residents had no shelter of the set in reach even
 * before the flood. They can never count as having lost access.
 */
export function commandNoReachLine(noReach: number, residents: number, share: number | null, language: Language): string {
  const part = roundModelFigure(noReach).text;
  const whole = roundModelFigure(residents).text;
  const percent = commandShareNote(share, residents);
  if (language === "th") return `ผู้อยู่อาศัย ${part} จาก ${whole} คน${percent} ไม่มีที่พักพิงของชุดนี้ในระยะเดิน 2 กม. ตั้งแต่ก่อนน้ำท่วม จึงไม่นับเป็นผู้สูญเสียการเข้าถึง`;
  return `${part} of ${whole} residents${percent} had no shelter of this set within 2 km before the flood, so they can never count as having lost access.`;
}

/** "Phahonyothin Rd (Hwy 1) ~12 km, Mae Sai bypass ~3 km": the named roads with impassable pieces in a subdistrict. */
export function commandRoadKmList(roads: readonly { name: string; km: number }[], language: Language, limit = 3): string {
  const shown = roads.slice(0, limit).map((road) => `${roadLabel(road, language)} ${roundModelKm(road.km).text} ${km(language)}`);
  const more = roads.length - shown.length;
  if (more <= 0) return shown.join(language === "th" ? " · " : ", ");
  return language === "th" ? `${shown.join(" · ")} และอีก ${more} สาย` : `${shown.join(", ")} and ${more} more`;
}

/** The figures of one subdistrict at the modelled peak, as the inspector lists them (rounded: the model is low confidence). */
export function commandPeakLines(
  peak: { floodedKm2: number; floodedShare: number | null; residentsInWater: number; roadKmImpassable: number; access: { withinReachBefore: number; lostAccess: number; lostShare: number | null } | null },
  language: Language,
): string[] {
  const th = language === "th";
  const area = peak.floodedKm2 < 0.05 ? "0" : `~${peak.floodedKm2.toFixed(1)}`;
  const share = peak.floodedShare === null ? "" : th ? ` (${commandPercent(peak.floodedShare)} ของตำบล)` : ` (${commandPercent(peak.floodedShare)} of the subdistrict)`;
  const water = roundModelFigure(peak.residentsInWater).text;
  const roads = roundModelKm(peak.roadKmImpassable).text;
  const lines = th
    ? [`น้ำตามแบบจำลองครอบคลุม ${area} ตร.กม.${share}`, `ผู้อยู่อาศัยในน้ำตามแบบจำลอง ${water} คน`, `ถนนสัญจรไม่ได้ ${roads} กม.`]
    : [`Modelled water over ${area} km²${share}`, `${water} residents in modelled water`, `${roads} km of roads impassable`];
  if (peak.access) {
    const lost = roundModelFigure(peak.access.lostAccess).text;
    const percent = commandShareNote(peak.access.lostShare, peak.access.withinReachBefore);
    lines.push(th
      ? `สูญเสียการเข้าถึงที่พักพิง ${lost} คน ${commandBaseText(peak.access.withinReachBefore, language)}${percent}`
      : `${lost} lost shelter access, ${commandBaseText(peak.access.withinReachBefore, language)}${percent}`);
  }
  return lines;
}

/** "9 more place records have no point and stay at district level." */
export function commandUnlocatedRecords(count: number, language: Language): string {
  if (language === "th") return `อีก ${count} รายการไม่มีจุดบนแผนที่ จึงแสดงเฉพาะในระดับอำเภอ`;
  return `${count} more place ${count === 1 ? "record has" : "records have"} no point and stay at district level.`;
}

/** The facts a class is shown with (decision-log rule R2): its tier and lane, the protocol versions and the anchors. */
export function commandPlanningFactLines(
  cell: { tier: string; lane: string | null; confidenceClass: string | null; fpps: number | null; reasonCode: string | null; floodInput: string | null; otherRows: number; sourceTimestamp: string },
  facts: { protocol: { v1a: string; v1b: string }; classRule: string; floodAnchor: number; vulnerabilityAnchors: { lower: string; lowerValue: number; upper: string; upperValue: number } },
  language: Language,
): string[] {
  const th = language === "th";
  const short = (hash: string) => hash.slice(0, 8);
  const anchors = facts.vulnerabilityAnchors;
  return [
    th
      ? `ชั้นหลักฐาน ${cell.tier}${cell.lane ? ` · ประเภทหลักฐาน ${cell.lane}` : ""}${cell.confidenceClass ? ` · ความเชื่อมั่น${cell.confidenceClass === "low" ? "ต่ำ" : "ปานกลาง"}` : ""}`
      : `Tier ${cell.tier}${cell.lane ? ` · lane ${cell.lane}` : ""}${cell.confidenceClass ? ` · confidence ${cell.confidenceClass}` : ""}`,
    ...(cell.fpps === null ? [] : [th ? `คะแนนการวางแผน (FPPS) ${cell.fpps.toFixed(1)} จาก 100` : `Planning score (FPPS) ${cell.fpps.toFixed(1)} of 100`]),
    ...(cell.reasonCode ? [th ? `รหัสเหตุผล ${cell.reasonCode}` : `Reason code ${cell.reasonCode}`] : []),
    th
      ? `หลักเกณฑ์ v1a ${short(facts.protocol.v1a)} · v1b ${short(facts.protocol.v1b)} · ${facts.classRule}`
      : `Protocol v1a ${short(facts.protocol.v1a)} · v1b ${short(facts.protocol.v1b)} · ${facts.classRule}`,
    th
      ? `ค่าอ้างอิง: สัดส่วนพื้นที่น้ำท่วม ${facts.floodAnchor.toFixed(2)} · สัดส่วนผู้พึ่งพิง ${anchors.lower} ${anchors.lowerValue.toFixed(3)} ถึง ${anchors.upper} ${anchors.upperValue.toFixed(3)}`
      : `Anchors: flooded share ${facts.floodAnchor.toFixed(2)} · dependent share ${anchors.lower} ${anchors.lowerValue.toFixed(3)} to ${anchors.upper} ${anchors.upperValue.toFixed(3)}`,
    ...(cell.floodInput
      ? [th
        ? `ข้อมูลน้ำท่วมที่ใช้: ${cell.floodInput}${cell.otherRows > 0 ? ` (อีก ${cell.otherRows} ชุดข้อมูลไม่ได้แสดง)` : ""}`
        : `Flood input: ${cell.floodInput}${cell.otherRows > 0 ? ` (${cell.otherRows} more ${cell.otherRows === 1 ? "input is" : "inputs are"} not shown)` : ""}`]
      : []),
    th ? `วันที่ของข้อมูล ${cell.sourceTimestamp}` : `Dated ${cell.sourceTimestamp}`,
  ];
}

// --- Find a place -----------------------------------------------------------------------------------------

export const COMMAND_FIND = {
  title: { en: "Find a place", th: "ค้นหาสถานที่" },
  field: { en: "Name of a place", th: "ชื่อสถานที่" },
  placeholder: { en: "Subdistrict, shelter, place, road", th: "ตำบล ที่พักพิง สถานที่ ถนน" },
  hint: {
    en: "Searches the names in the replay data: subdistricts, reported shelters, place records, named facilities and named roads. The data holds no list of villages or sois.",
    th: "ค้นจากชื่อที่มีในข้อมูลการย้อนดู: ตำบล ที่พักพิงตามรายงาน รายการตามสถานที่ สถานที่สำคัญที่มีชื่อ และถนนที่มีชื่อ ข้อมูลไม่มีรายชื่อหมู่บ้านหรือซอย",
  },
  none: { en: "No name in the replay data matches.", th: "ไม่พบชื่อที่ตรงกันในข้อมูลการย้อนดู" },
  noPoint: { en: "no point in the data", th: "ไม่มีจุดในข้อมูล" },
  results: { en: "Names found", th: "ชื่อที่พบ" },
  close: { en: "Close", th: "ปิด" },
  found: { en: "Found place", th: "สถานที่ที่พบ" },
} as const satisfies Record<string, Localized>;

/** What kind of name a search result is. A place record is a place news reported water at, not a surveyed site. */
export const COMMAND_FIND_KIND: Readonly<Record<"tambon" | "shelter" | "command_centre" | "place_record" | "road", Localized>> = {
  tambon: { en: "Subdistrict", th: "ตำบล" },
  shelter: { en: "Shelter reported in 2024", th: "ที่พักพิงตามรายงานปี 2567 (2024)" },
  command_centre: { en: "Command centre (reported)", th: "ศูนย์บัญชาการ (ตามรายงาน)" },
  place_record: { en: "Place record (news, not surveyed)", th: "รายการตามสถานที่ (จากข่าว ไม่ได้สำรวจ)" },
  road: { en: "Road", th: "ถนน" },
};

/** The kind line of a search result: "Shelter reported in 2024", "School", "Place record (news, not surveyed) · 2 records". */
export function commandFindKindText(entry: { kind: "tambon" | "shelter" | "command_centre" | "place_record" | "facility" | "road"; facilityType: string | null; records: number }, language: Language): string {
  if (entry.kind === "facility") return commandFacilityType(entry.facilityType ?? "", language) || pick(COMMAND_TOOLS.facilities, language);
  const kind = pick(COMMAND_FIND_KIND[entry.kind], language);
  if (entry.kind !== "place_record" || entry.records <= 1) return kind;
  return language === "th" ? `${kind} · ${entry.records} รายการ` : `${kind} · ${entry.records} records`;
}

/** "3 names" / "พบ 3 ชื่อ": the count a screen reader hears while typing. */
export function commandFindCount(count: number, language: Language): string {
  if (language === "th") return `พบ ${count} ชื่อ`;
  return `${count} ${count === 1 ? "name" : "names"}`;
}

/** "placed to within ±150 m": how closely a place record is located. */
export function commandToleranceText(metres: number, language: Language): string {
  return language === "th" ? `ตำแหน่งคลาดเคลื่อนได้ ±${metres} ม.` : `placed to within ±${metres} m`;
}
