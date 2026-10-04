/**
 * Wording of the act flow of the Command exercise replay (Mae Sai, September 2024), in English and Thai: the action
 * bar of an invented item, where people go and how to get near, the facilitator's setup, the brief sheet, the
 * exercise log and the help steps.
 *
 * The page states facts and gives no advice on the kind of team to send. Nothing here calls an item checked or
 * proven, a distance is a straight line and never a route, and every action is an action of an exercise that stays
 * on the device. Each string is scanned by the shared wording lint.
 *
 * Thai: written by an AI assistant in the plain register of Thai public disaster notices; no native speaker has
 * reviewed it (owner decision, 5 Oct 2026), and the information drawer says so.
 */

import { formatDateWithYear, type Language, type Localized } from "./flood-timeline";
import { commandDistanceBearing, commandDistanceText, commandRoadName, type DepthFact, type ItemFacts, type NearRoad, type NearSite, type SiteUse } from "./flood-timeline-command-brief";
import { COMMAND_LEGEND, COMMAND_MAP, commandMomentShort } from "./flood-timeline-command-copy";
import type { ExerciseUrgency } from "./flood-timeline-command-incidents";
import {
  CALLSIGN_MAX_LENGTH,
  COMMAND_LOG_SIMULATED_COLUMN,
  ROSTER_MAX_TEAMS,
  type CallsignProblem,
  type CommandLogAction,
  type CommandLogEntry,
  type CommandRole,
  type CommandUndo,
  type DropReason,
  type TeamType,
} from "./flood-timeline-command-log";
import { COMMAND_URGENCY } from "./flood-timeline-command-reports-copy";

const pick = (text: Localized, language: Language): string => (language === "th" ? text.th : text.en);

// --- The action bar and the handling of an item ----------------------------------------------------------

export const COMMAND_ACT = {
  barLabel: { en: "Actions on this exercise item", th: "การดำเนินการกับรายการฝึกซ้อมนี้" },
  assign: { en: "Assign", th: "มอบหมาย" },
  brief: { en: "Brief", th: "ข้อความสรุป" },
  done: { en: "Done", th: "เสร็จสิ้น" },
  reopen: { en: "Reopen", th: "เปิดใหม่" },
  more: { en: "More actions", th: "การดำเนินการอื่น" },
  acknowledge: { en: "Acknowledge", th: "รับทราบ" },
  dropAs: { en: "Drop as", th: "ยุติเพราะ" },
  raise: { en: "Raise the urgency one step", th: "เพิ่มระดับความเร่งด่วนหนึ่งขั้น" },
  lower: { en: "Lower the urgency one step", th: "ลดระดับความเร่งด่วนหนึ่งขั้น" },
  pickTitle: { en: "Assign to a callsign", th: "มอบหมายให้นามเรียกขาน" },
  pickNote: {
    en: "The roster is typed on this device. The page gives no advice on the kind of team to send.",
    th: "รายชื่อนี้พิมพ์ไว้ในอุปกรณ์เครื่องนี้ หน้านี้ไม่แนะนำว่าควรส่งชุดปฏิบัติการประเภทใด",
  },
  rosterEmpty: { en: "The roster is empty. Add callsigns in the exercise setup.", th: "ยังไม่มีนามเรียกขานในรายชื่อ เพิ่มได้ที่หน้าตั้งค่าการฝึกซ้อม" },
  editRoster: { en: "Edit the roster", th: "แก้ไขรายชื่อ" },
  undo: { en: "Undo", th: "เลิกทำ" },
  cancel: { en: "Cancel", th: "ยกเลิก" },
  closedNote: { en: "The item is closed. Reopen it to assign it again.", th: "รายการนี้ปิดแล้ว เปิดใหม่ก่อนจึงจะมอบหมายได้อีก" },
  deviceNoActions: {
    en: "No team is assigned to a report saved on this device, and no brief is built from it: it is dated today, outside the 2024 replay, and it names a subdistrict and no point.",
    th: "ไม่มีการมอบหมายชุดปฏิบัติการให้รายงานที่บันทึกไว้ในอุปกรณ์เครื่องนี้ และไม่สร้างข้อความสรุปจากรายงานนี้ เพราะรายงานลงวันที่ปัจจุบัน อยู่นอกการย้อนดูเหตุการณ์ปี 2567 (2024) และระบุเพียงตำบล ไม่มีจุดบนแผนที่",
  },
  resetNotice: { en: "Exercise reset on this device", th: "ล้างข้อมูลการฝึกซ้อมในอุปกรณ์เครื่องนี้แล้ว" },
  pickStaging: { en: "Tap the map where the team starts", th: "แตะแผนที่ตรงจุดที่ชุดปฏิบัติการเริ่มออกเดินทาง" },
} as const satisfies Record<string, Localized>;

export const COMMAND_DROP_REASON: Readonly<Record<DropReason, Localized>> = {
  duplicate: { en: "duplicate", th: "รายการซ้ำ" },
  unreachable: { en: "could not reach", th: "เข้าไม่ถึง" },
};

export const COMMAND_TEAM_TYPE: Readonly<Record<TeamType, Localized>> = {
  boat: { en: "Boat", th: "เรือ" },
  wading: { en: "Wading", th: "เดินลุยน้ำ" },
  vehicle: { en: "Vehicle", th: "ยานพาหนะ" },
  medical: { en: "Medical", th: "การแพทย์" },
};

/** "Drop as: duplicate" / "ยุติเพราะ: รายการซ้ำ". */
export function commandDropLabel(reason: DropReason, language: Language): string {
  return `${pick(COMMAND_ACT.dropAs, language)}: ${pick(COMMAND_DROP_REASON[reason], language)}`;
}

/** What a roster chip says to a screen reader: "Assign to BOAT-2 (Boat)". */
export function commandAssignTo(callsign: string, type: TeamType, language: Language): string {
  return language === "th" ? `มอบหมายให้ ${callsign} (${pick(COMMAND_TEAM_TYPE[type], language)})` : `Assign to ${callsign} (${pick(COMMAND_TEAM_TYPE[type], language)})`;
}

/** "Changed on this device: Urgent → Life at risk" under the urgency of an item whose urgency the operator moved. */
export function commandUrgencyChanged(author: ExerciseUrgency, now: ExerciseUrgency, language: Language): string {
  const from = pick(COMMAND_URGENCY[author], language);
  const to = pick(COMMAND_URGENCY[now], language);
  return language === "th" ? `เปลี่ยนในอุปกรณ์เครื่องนี้: ${from} → ${to}` : `Changed on this device: ${from} → ${to}`;
}

/**
 * The one line that says what an action did, beside its Undo: "EX-05 assigned to BOAT-2", "EX-05 done",
 * "EX-05 dropped: duplicate", "EX-05 urgency: Urgent → Life at risk".
 */
export function commandActionNotice(undo: Pick<CommandUndo, "itemId" | "action" | "before" | "after">, authorUrgency: ExerciseUrgency, language: Language): string {
  const th = language === "th";
  const id = undo.itemId;
  switch (undo.action) {
    case "assigned": return th ? `มอบหมาย ${id} ให้ ${undo.after.callsign ?? ""} แล้ว` : `${id} assigned to ${undo.after.callsign ?? ""}`;
    case "acknowledged": return th ? `รับทราบ ${id} แล้ว` : `${id} acknowledged`;
    case "done": return th ? `${id} เสร็จสิ้นแล้ว` : `${id} done`;
    case "dropped": return th ? `ยุติ ${id}: ${pick(COMMAND_DROP_REASON[undo.after.reason ?? "duplicate"], language)}` : `${id} dropped: ${pick(COMMAND_DROP_REASON[undo.after.reason ?? "duplicate"], language)}`;
    case "reopened": return th ? `เปิด ${id} ใหม่แล้ว` : `${id} reopened`;
    case "urgency_raised":
    case "urgency_lowered": {
      const from = pick(COMMAND_URGENCY[undo.before?.urgency ?? authorUrgency], language);
      const to = pick(COMMAND_URGENCY[undo.after.urgency ?? authorUrgency], language);
      return th ? `${id} ระดับความเร่งด่วน: ${from} → ${to}` : `${id} urgency: ${from} → ${to}`;
    }
    default: return id;
  }
}

// --- Where people go -------------------------------------------------------------------------------------

export const COMMAND_GO = {
  title: { en: "Where people go", th: "ที่พักพิงใกล้จุดนี้" },
  dry: { en: "dry in the model at this stage", th: "แห้งตามแบบจำลอง ณ ระดับน้ำนี้" },
  wet: { en: "in modelled water at this stage", th: "อยู่ในน้ำตามแบบจำลอง ณ ระดับน้ำนี้" },
  openingUnknown: { en: "opening time not known", th: "ไม่ทราบเวลาที่เริ่มเปิดใช้" },
  occupancyHeld: {
    en: "Occupancy counts carry later dates, so they are shown in hindsight mode.",
    th: "จำนวนผู้พักพิงตามรายงานมีวันที่หลังชั่วโมงนี้ จึงแสดงในโหมดมองย้อนหลัง",
  },
  none: { en: "The replay data holds no counted site with a point.", th: "ข้อมูลการย้อนดูไม่มีที่พักพิงที่นับและมีจุดบนแผนที่" },
  limit: {
    en: "Straight-line distances. Nothing here says that a site could be reached, was in use at this hour or had room.",
    th: "เป็นระยะเส้นตรง ข้อมูลนี้ไม่ได้บอกว่าเดินทางไปถึงได้ ใช้งานอยู่ ณ ชั่วโมงนี้ หรือยังมีที่ว่าง",
  },
  nodeLead: { en: "Access model", th: "แบบจำลองการเข้าถึง" },
  nodeNone: { en: "no resident node within 300 m of this point", th: "ไม่มีจุดผู้อยู่อาศัยในระยะ 300 ม. จากจุดนี้" },
  nodeKept: { en: "access to a shelter of the 2024 set kept at this stage", th: "ยังเข้าถึงที่พักพิงของชุดปี 2567 (2024) ได้ ณ ระดับน้ำนี้" },
  nodeLost: { en: "access to a shelter of the 2024 set lost at this stage", th: "สูญเสียการเข้าถึงที่พักพิงของชุดปี 2567 (2024) ณ ระดับน้ำนี้" },
  nodeNoneBefore: { en: "no shelter of the 2024 set within a 2 km walk even before the flood", th: "ไม่มีที่พักพิงของชุดปี 2567 (2024) ในระยะเดิน 2 กม. ตั้งแต่ก่อนน้ำท่วม" },
} as const satisfies Record<string, Localized>;

/** "3 nearest of the 12 counted sites · straight line". The count of sites is the data's, so it keeps plain digits. */
export function commandGoMeta(shown: number, counted: number, language: Language): string {
  return language === "th" ? `${shown} แห่งที่ใกล้ที่สุดจาก ${counted} แห่งที่นับ · ระยะเส้นตรง` : `${shown} nearest of the ${counted} counted sites · straight line`;
}

/**
 * "reported in use by 15 Sep 2024; opening time not known": a bound of the data reads "by", an exact day "from". In
 * trainee mode the day of the first 2024 source stands in their place ("first reported in use on 11 Sep 2024"), so
 * no later date is shown. The text of the data is used when it gives no date.
 */
export function commandReportedInUse(use: SiteUse, language: Language): string {
  const tail = pick(COMMAND_GO.openingUnknown, language);
  if (use.kind === "text") return language === "th" ? `มีรายงานว่าใช้งาน: ${use.text} · ${tail}` : `reported in use: ${use.text}; ${tail}`;
  const date = formatDateWithYear(use.date, language);
  if (language === "th") {
    const lead = use.kind === "by" ? `มีรายงานว่าใช้งานแล้วภายในวันที่ ${date}` : use.kind === "from" ? `มีรายงานว่าใช้งานตั้งแต่วันที่ ${date}` : `มีรายงานการใช้ครั้งแรกเมื่อวันที่ ${date}`;
    return `${lead} · ${tail}`;
  }
  return `${use.kind === "first_report" ? "first reported in use on" : `reported in use ${use.kind}`} ${date}; ${tail}`;
}

/** The state of a site in the model at this stage, in words. */
export function commandSiteState(state: NearSite["state"], language: Language): string {
  return pick(state === "wet" ? COMMAND_GO.wet : state === "dry" ? COMMAND_GO.dry : COMMAND_MAP.notModelled, language);
}

/** The one line from the access model: the nearest resident node within 300 m, and what the model says of it. */
export function commandNodeLine(node: ItemFacts["node"], language: Language): string {
  const lead = pick(COMMAND_GO.nodeLead, language);
  if (!node) return `${lead}: ${pick(COMMAND_GO.nodeNone, language)}`;
  const access = pick(node.access === "kept" ? COMMAND_GO.nodeKept : node.access === "lost" ? COMMAND_GO.nodeLost : COMMAND_GO.nodeNoneBefore, language);
  const away = commandDistanceText(node.distanceM, language);
  return language === "th" ? `${lead} จุดผู้อยู่อาศัยห่าง ${away}: ${access}` : `${lead}, resident node ${away} away: ${access}`;
}

// --- How to get near -------------------------------------------------------------------------------------

export const COMMAND_NEAR = {
  title: { en: "How to get near", th: "การเข้าถึงจุดนี้" },
  factsOnly: { en: "facts only", th: "ข้อเท็จจริงเท่านั้น" },
  over: { en: "At or over the 0.3 m level at which roads count as impassable.", th: "ถึงหรือเกินระดับ 0.3 ม. ที่นับว่าถนนสัญจรไม่ได้" },
  under: { en: "Under the 0.3 m level at which roads count as impassable.", th: "ต่ำกว่าระดับ 0.3 ม. ที่นับว่าถนนสัญจรไม่ได้" },
  roadLead: { en: "Nearest road piece under 0.3 m in the model", th: "ช่วงถนนที่ใกล้ที่สุดซึ่งน้ำต่ำกว่า 0.3 ม. ตามแบบจำลอง" },
  roadNone: { en: "The model has no road piece under 0.3 m.", th: "แบบจำลองไม่มีช่วงถนนที่น้ำต่ำกว่า 0.3 ม." },
  roadLimit: { en: "Not checked for a connected way out; bridge decks not modelled.", th: "ไม่ได้ตรวจว่ามีทางเชื่อมต่อออกไปได้หรือไม่ และไม่ได้จำลองพื้นสะพาน" },
  noNamedRoads: { en: "No named road is impassable in this subdistrict this hour (model).", th: "ชั่วโมงนี้ไม่มีถนนที่มีชื่อในตำบลนี้สัญจรไม่ได้ (ตามแบบจำลอง)" },
  stagingLead: { en: "From the staging point", th: "จากจุดระดมทรัพยากร" },
  stagingOnMap: { en: "point set on the map", th: "จุดที่กำหนดบนแผนที่" },
  straightLine: { en: "straight line, not a route", th: "เส้นตรง ไม่ใช่เส้นทาง" },
  legendStaging: { en: "staging point of the exercise (set by the facilitator)", th: "จุดระดมทรัพยากรของการฝึกซ้อม (ผู้อำนวยการฝึกกำหนด)" },
  legendLine: { en: "straight line from the staging point to the selected item: not a route", th: "เส้นตรงจากจุดระดมทรัพยากรถึงรายการที่เลือก ไม่ใช่เส้นทาง" },
  noAdvice: {
    en: "The page gives no advice on the kind of team to send: the model has depth and no current.",
    th: "หน้านี้ไม่แนะนำว่าควรส่งชุดปฏิบัติการประเภทใด เพราะแบบจำลองมีเพียงความลึกของน้ำ ไม่มีกระแสน้ำ",
  },
} as const satisfies Record<string, Localized>;

/** Whether the model has the point at or over the 0.3 m level; null where it has no water or no value. */
export function commandDepthFactLine(fact: DepthFact, language: Language): string | null {
  if (fact === "at_or_over") return pick(COMMAND_NEAR.over, language);
  if (fact === "under") return pick(COMMAND_NEAR.under, language);
  return null;
}

/** "Nearest road piece under 0.3 m in the model: Phahonyothin Rd (Hwy 1), ~120 m away (dry)". */
export function commandRoadFact(road: NearRoad | null, language: Language): string {
  if (!road) return pick(COMMAND_NEAR.roadNone, language);
  const state = pick(road.state === "dry" ? COMMAND_LEGEND.roadDry : COMMAND_LEGEND.roadWet, language);
  const away = commandDistanceText(road.distanceM, language);
  return language === "th"
    ? `${pick(COMMAND_NEAR.roadLead, language)}: ${commandRoadName(road.name, language)} ห่าง ${away} (${state})`
    : `${pick(COMMAND_NEAR.roadLead, language)}: ${commandRoadName(road.name, language)}, ${away} away (${state})`;
}

/** "Named roads impassable in Mae Sai subdistrict this hour" / "ถนนที่มีชื่อซึ่งสัญจรไม่ได้ใน ต.แม่สาย ชั่วโมงนี้". */
export function commandImpassableLead(tambon: Localized | null, language: Language): string {
  if (language === "th") return tambon ? `ถนนที่มีชื่อซึ่งสัญจรไม่ได้ใน ต.${tambon.th} ชั่วโมงนี้` : "ถนนที่มีชื่อซึ่งสัญจรไม่ได้ในตำบลนี้ ชั่วโมงนี้";
  return tambon ? `Named roads impassable in ${tambon.en} subdistrict this hour` : "Named roads impassable in this subdistrict this hour";
}

/** The name of the staging point: the site it is at, or that it was set on the map. */
export function commandStagingName(staging: { name: Localized | null }, language: Language): string {
  return staging.name ? pick(staging.name, language) : pick(COMMAND_NEAR.stagingOnMap, language);
}

/** "From the staging point (Mae Sai District Office): ~1.4 km · north-east". */
export function commandStagingLine(staging: NonNullable<ItemFacts["staging"]>, language: Language): string {
  return `${pick(COMMAND_NEAR.stagingLead, language)} (${commandStagingName(staging.point, language)}): ${commandDistanceBearing(staging.distanceM, staging.compass, language)}`;
}

/** The label on the dashed line of the map: "straight line, not a route · ~1.4 km". */
export function commandLineLabel(metres: number, language: Language): string {
  return `${pick(COMMAND_NEAR.straightLine, language)} · ${commandDistanceText(metres, language)}`;
}

// --- The facilitator's setup -----------------------------------------------------------------------------

export const COMMAND_SETUP = {
  title: { en: "Exercise setup", th: "ตั้งค่าการฝึกซ้อม" },
  intro: { en: "For the facilitator of an exercise.", th: "สำหรับผู้อำนวยการฝึก" },
  deviceOnly: { en: "Saved on this device only", th: "บันทึกไว้ในอุปกรณ์เครื่องนี้เท่านั้น" },
  roster: { en: "Roster", th: "รายชื่อชุดปฏิบัติการ" },
  rosterRule: {
    en: "Callsigns only: no names and no phone numbers. At most 12 characters; an entry with seven or more digits is refused.",
    th: "ใช้นามเรียกขานเท่านั้น ไม่ใส่ชื่อบุคคลหรือหมายเลขโทรศัพท์ ยาวไม่เกิน 12 ตัวอักษร และไม่รับข้อความที่มีตัวเลขตั้งแต่ 7 หลักขึ้นไป",
  },
  rosterExample: { en: "A device starts with five example callsigns. They name no real unit.", th: "อุปกรณ์แต่ละเครื่องเริ่มต้นด้วยนามเรียกขานตัวอย่าง 5 ชุด ซึ่งไม่ใช่ชื่อหน่วยงานจริง" },
  callsign: { en: "Callsign", th: "นามเรียกขาน" },
  type: { en: "Kind of team", th: "ประเภทชุดปฏิบัติการ" },
  add: { en: "Add", th: "เพิ่ม" },
  staging: { en: "Staging point", th: "จุดระดมทรัพยากร" },
  stagingNote: {
    en: "Where the team starts. The map draws a dashed straight line from it to the selected item: a straight line, not a route.",
    th: "จุดที่ชุดปฏิบัติการเริ่มออกเดินทาง แผนที่จะลากเส้นประจากจุดนี้ไปยังรายการที่เลือก ซึ่งเป็นเส้นตรง ไม่ใช่เส้นทาง",
  },
  stagingReported: { en: "reported in use in 2024", th: "มีรายงานว่าใช้ในปี 2567 (2024)" },
  stagingPoint: { en: "A point on the map", th: "จุดบนแผนที่" },
  stagingPick: { en: "Pick on the map", th: "เลือกบนแผนที่" },
  stagingNotSet: { en: "not set yet", th: "ยังไม่ได้กำหนด" },
  start: { en: "Start hour", th: "ชั่วโมงเริ่มต้น" },
  startUseNow: { en: "Use the hour on screen", th: "ใช้ชั่วโมงที่แสดงอยู่" },
  startGo: { en: "Start the exercise from this hour", th: "เริ่มการฝึกซ้อมจากชั่วโมงนี้" },
  startNote: { en: "The replay goes to this hour and pauses. How the items were handled is kept until the exercise is reset.", th: "การย้อนดูจะไปที่ชั่วโมงนี้และหยุดรอ สถานะของรายการต่าง ๆ ยังคงอยู่จนกว่าจะล้างข้อมูลการฝึกซ้อม" },
  shows: { en: "What the exercise shows", th: "สิ่งที่การฝึกซ้อมแสดง" },
  speed: { en: "Playback speed", th: "ความเร็วในการเล่น" },
  reset: { en: "Reset exercise", th: "ล้างข้อมูลการฝึกซ้อม" },
  resetNote: {
    en: "Clears the roster, the setup, how each item was handled and the log from this device. The replay data stays as it is.",
    th: "ลบรายชื่อ การตั้งค่า สถานะของแต่ละรายการ และบันทึกการฝึกซ้อมออกจากอุปกรณ์เครื่องนี้ ข้อมูลการย้อนดูยังคงเดิม",
  },
} as const satisfies Record<string, Localized>;

export const COMMAND_CALLSIGN_PROBLEM: Readonly<Record<CallsignProblem, Localized>> = {
  empty: { en: "Type a callsign.", th: "พิมพ์นามเรียกขาน" },
  digits: { en: "Refused: seven or more digits. A callsign is not a phone number.", th: "ไม่รับ: มีตัวเลขตั้งแต่ 7 หลักขึ้นไป นามเรียกขานไม่ใช่หมายเลขโทรศัพท์" },
  too_long: { en: `At most ${CALLSIGN_MAX_LENGTH} characters.`, th: `ยาวไม่เกิน ${CALLSIGN_MAX_LENGTH} ตัวอักษร` },
  characters: { en: "Letters, digits, spaces and hyphens only, starting with a letter or a digit.", th: "ใช้ได้เฉพาะตัวอักษร ตัวเลข ช่องว่าง และขีดกลาง โดยขึ้นต้นด้วยตัวอักษรหรือตัวเลข" },
  duplicate: { en: "Already on the roster.", th: "มีนามเรียกขานนี้ในรายชื่อแล้ว" },
  roster_full: { en: `The roster holds ${ROSTER_MAX_TEAMS} callsigns at most.`, th: `รายชื่อมีได้ไม่เกิน ${ROSTER_MAX_TEAMS} นามเรียกขาน` },
};

/** "Remove BOAT-1" / "ลบ BOAT-1". */
export function commandRemoveTeam(callsign: string, language: Language): string {
  return language === "th" ? `ลบ ${callsign}` : `Remove ${callsign}`;
}

/** "20.4281, 99.8832": a point the facilitator tapped, to four decimals. */
export function commandPointText(point: { lat: number; lon: number }): string {
  return `${point.lat.toFixed(4)}, ${point.lon.toFixed(4)}`;
}

// --- The brief sheet -------------------------------------------------------------------------------------

export const COMMAND_BRIEF = {
  itemTitle: { en: "Brief", th: "ข้อความสรุป" },
  situationTitle: { en: "Situation brief", th: "สรุปสถานการณ์" },
  language: { en: "Language of the brief", th: "ภาษาของข้อความสรุป" },
  thai: { en: "Thai", th: "ไทย" },
  english: { en: "English", th: "อังกฤษ" },
  text: { en: "Text of the brief", th: "เนื้อความของข้อความสรุป" },
  rule: {
    en: "The exercise tag is the first and the last line. A brief holds no rain value, no note of a report and no statement of a place record.",
    th: "บรรทัดแรกและบรรทัดสุดท้ายเป็นป้ายการฝึกซ้อมเสมอ ข้อความสรุปไม่มีค่าปริมาณฝน บันทึกข้อความของรายงาน หรือข้อความของรายการตามสถานที่",
  },
  share: { en: "Share", th: "แชร์" },
  copy: { en: "Copy", th: "คัดลอก" },
  copied: { en: "Copied", th: "คัดลอกแล้ว" },
  copyFailed: { en: "Could not copy. Select the text and copy it by hand.", th: "คัดลอกไม่สำเร็จ โปรดเลือกข้อความแล้วคัดลอกเอง" },
  smsTitle: { en: "Short version for a text message", th: "ฉบับสั้นสำหรับ SMS" },
  smsOpen: { en: "Open in the message app", th: "เปิดในแอปข้อความ" },
  smsNoRecipient: { en: "No recipient is filled in: you type the number.", th: "ไม่มีการกรอกหมายเลขผู้รับไว้ให้ ต้องพิมพ์หมายเลขเอง" },
  sends: {
    en: "FloodGuard sends nothing. A brief leaves this device only through the app you pick.",
    th: "FloodGuard ไม่ส่งข้อมูลใดออกไป ข้อความสรุปจะออกจากอุปกรณ์เครื่องนี้ผ่านแอปที่ท่านเลือกเท่านั้น",
  },
  open: { en: "Open the situation brief", th: "เปิดสรุปสถานการณ์" },
} as const satisfies Record<string, Localized>;

/** "Brief · EX-05" / "ข้อความสรุป · EX-05"; the situation brief has its own title. */
export function commandBriefTitle(itemId: string | null, language: Language): string {
  return itemId ? `${pick(COMMAND_BRIEF.itemTitle, language)} · ${itemId}` : pick(COMMAND_BRIEF.situationTitle, language);
}

/** "9 lines" / "9 บรรทัด". */
export function commandBriefLineCount(lines: number, language: Language): string {
  return language === "th" ? `${lines} บรรทัด` : `${lines} ${lines === 1 ? "line" : "lines"}`;
}

/** "102 of 134 characters · 2 parts" / "102 จาก 134 ตัวอักษร · นับเป็น 2 ข้อความ". */
export function commandSmsCount(characters: number, limit: number, parts: number, language: Language): string {
  if (language === "th") return `${characters} จาก ${limit} ตัวอักษร · นับเป็น ${parts} ข้อความ`;
  return `${characters} of ${limit} characters · ${parts} ${parts === 1 ? "part" : "parts"}`;
}

// --- The exercise menu and the log -----------------------------------------------------------------------

export const COMMAND_EXERCISE_MENU = {
  label: { en: "Exercise", th: "การฝึกซ้อม" },
  menu: { en: "Exercise: setup, log and situation brief", th: "การฝึกซ้อม: ตั้งค่า บันทึก และสรุปสถานการณ์" },
  setup: { en: "Exercise setup", th: "ตั้งค่าการฝึกซ้อม" },
  log: { en: "Exercise log", th: "บันทึกการฝึกซ้อม" },
  situation: { en: "Situation brief", th: "สรุปสถานการณ์" },
} as const satisfies Record<string, Localized>;

export const COMMAND_LOG = {
  title: { en: "Exercise log", th: "บันทึกการฝึกซ้อม" },
  intro: {
    en: "Every action taken in this exercise on this device, newest first. Every row is an exercise action: none is a real dispatch.",
    th: "ทุกการดำเนินการในการฝึกซ้อมนี้บนอุปกรณ์เครื่องนี้ เรียงจากล่าสุด ทุกแถวเป็นการดำเนินการในการฝึกซ้อม ไม่ใช่การสั่งการจริง",
  },
  replay: { en: "Replay time", th: "เวลาในการย้อนดู" },
  device: { en: "Device time", th: "เวลาของอุปกรณ์" },
  role: { en: "Role", th: "บทบาท" },
  callsign: { en: "Callsign", th: "นามเรียกขาน" },
  action: { en: "Action", th: "การดำเนินการ" },
  empty: { en: "Nothing has been done in this exercise yet.", th: "ยังไม่มีการดำเนินการในการฝึกซ้อมนี้" },
  export: { en: "Export CSV", th: "ส่งออกไฟล์ CSV" },
  exportNote: {
    en: `The file has a column "${COMMAND_LOG_SIMULATED_COLUMN}" that is true on every row. It holds no rain value and no note of a report.`,
    th: `ไฟล์มีคอลัมน์ "${COMMAND_LOG_SIMULATED_COLUMN}" ซึ่งเป็น true ทุกแถว และไม่มีค่าปริมาณฝนหรือบันทึกข้อความของรายงาน`,
  },
} as const satisfies Record<string, Localized>;

export const COMMAND_ROLE: Readonly<Record<CommandRole, Localized>> = {
  coordinator: { en: "Coordinator", th: "ผู้ประสานงาน" },
  facilitator: { en: "Facilitator", th: "ผู้อำนวยการฝึก" },
};

export const COMMAND_LOG_ACTION: Readonly<Record<CommandLogAction, Localized>> = {
  acknowledged: { en: "acknowledged", th: "รับทราบ" },
  assigned: { en: "assigned", th: "มอบหมาย" },
  done: { en: "done", th: "เสร็จสิ้น" },
  dropped: { en: "dropped", th: "ยุติ" },
  reopened: { en: "reopened", th: "เปิดใหม่" },
  urgency_raised: { en: "urgency raised", th: "เพิ่มระดับความเร่งด่วน" },
  urgency_lowered: { en: "urgency lowered", th: "ลดระดับความเร่งด่วน" },
  undone: { en: "undone", th: "เลิกทำ" },
  brief_shown: { en: "brief opened", th: "เปิดข้อความสรุป" },
  brief_shared: { en: "brief shared", th: "แชร์ข้อความสรุป" },
  brief_copied: { en: "brief copied", th: "คัดลอกข้อความสรุป" },
  brief_sms: { en: "brief handed to the message app", th: "ส่งข้อความสรุปไปยังแอปข้อความ" },
  situation_brief: { en: "situation brief opened", th: "เปิดสรุปสถานการณ์" },
  setup_changed: { en: "setup changed", th: "เปลี่ยนการตั้งค่า" },
  exercise_started: { en: "exercise started", th: "เริ่มการฝึกซ้อม" },
  log_exported: { en: "log exported", th: "ส่งออกบันทึก" },
};

/** What a setup row of the log changed. */
export const COMMAND_SETUP_PART: Readonly<Record<string, Localized>> = {
  roster: { en: "roster", th: "รายชื่อ" },
  staging: { en: "staging point", th: "จุดระดมทรัพยากร" },
  start: { en: "start hour", th: "ชั่วโมงเริ่มต้น" },
  mode: { en: "what the exercise shows", th: "สิ่งที่การฝึกซ้อมแสดง" },
  items: { en: "exercise items", th: "รายการฝึกซ้อม" },
  speed: { en: "playback speed", th: "ความเร็วในการเล่น" },
  pause: { en: "pause on a life-at-risk item", th: "การหยุดเมื่อมีรายการเสี่ยงต่อชีวิต" },
};

const urgencyOf = (code: string): ExerciseUrgency | null => (code === "life_at_risk" || code === "urgent" || code === "information" ? code : null);

/** The action of a log row in words, with its item and what its detail code stands for: "EX-05 dropped: duplicate". */
export function commandLogActionText(entry: Pick<CommandLogEntry, "action" | "itemId" | "detail">, language: Language): string {
  const action = pick(COMMAND_LOG_ACTION[entry.action], language);
  const lead = entry.itemId ? `${entry.itemId} ${action}` : action;
  const { detail } = entry;
  if (!detail) return lead;
  if (entry.action === "dropped" && (detail === "duplicate" || detail === "unreachable")) return `${lead}: ${pick(COMMAND_DROP_REASON[detail], language)}`;
  if (entry.action === "urgency_raised" || entry.action === "urgency_lowered") {
    const [from, to] = detail.split(">").map(urgencyOf);
    return from && to ? `${lead}: ${pick(COMMAND_URGENCY[from], language)} → ${pick(COMMAND_URGENCY[to], language)}` : lead;
  }
  if (entry.action === "undone" && detail in COMMAND_LOG_ACTION) return `${lead}: ${pick(COMMAND_LOG_ACTION[detail as CommandLogAction], language)}`;
  if (entry.action === "setup_changed" && detail in COMMAND_SETUP_PART) return `${lead}: ${pick(COMMAND_SETUP_PART[detail], language)}`;
  if (detail === "th" || detail === "en") return `${lead} (${pick(detail === "th" ? COMMAND_BRIEF.thai : COMMAND_BRIEF.english, language)})`;
  return lead;
}

/** "Showing the newest 50 of 132 rows; the export holds them all." */
export function commandLogShown(shown: number, total: number, language: Language): string {
  if (language === "th") return shown < total ? `แสดง ${shown} แถวล่าสุดจากทั้งหมด ${total} แถว ไฟล์ส่งออกมีครบทุกแถว` : `ทั้งหมด ${total} แถว`;
  return shown < total ? `Showing the newest ${shown} of ${total} rows; the export holds them all.` : `${total} ${total === 1 ? "row" : "rows"}`;
}

/** The replay time of a log row: "12 Sep 12:00 ICT". */
export const commandLogReplayTime = (hour: number, language: Language): string => commandMomentShort(hour, language);

/**
 * The time of this device of a log row, in the device's own time zone: "5 Oct 10:40:12". It is a time of today's
 * world and never sits on the replay clock.
 */
export function commandDeviceTime(iso: string, language: Language, timeZone?: string): string {
  const instant = new Date(iso);
  if (Number.isNaN(instant.getTime())) return iso;
  return new Intl.DateTimeFormat(language === "th" ? "th-TH-u-ca-gregory-nu-latn" : "en-GB", {
    day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false, timeZone,
  }).format(instant);
}

// --- Help: from seeing to acting -------------------------------------------------------------------------

export const COMMAND_HELP_ACT = {
  title: { en: "From seeing to acting", th: "จากการอ่านสถานการณ์สู่การสั่งการในการฝึกซ้อม" },
  step1: {
    en: "The facilitator sets the roster, the staging point and the start hour in the exercise setup (the Exercise menu).",
    th: "ผู้อำนวยการฝึกกำหนดรายชื่อชุดปฏิบัติการ จุดระดมทรัพยากร และชั่วโมงเริ่มต้น ที่หน้าตั้งค่าการฝึกซ้อม (เมนูการฝึกซ้อม)",
  },
  step2: {
    en: "Select a marker. The detail states the depth in the model, the nearest counted shelters and how to get near: facts only, no advice.",
    th: "เลือกเครื่องหมายบนแผนที่ รายละเอียดจะบอกความลึกของน้ำตามแบบจำลอง ที่พักพิงที่ใกล้ที่สุด และข้อเท็จจริงเกี่ยวกับการเข้าถึงจุดนั้น โดยไม่มีคำแนะนำ",
  },
  step3: {
    en: "Assign a callsign, then open the brief: share it, copy it, or hand the short version to the message app.",
    th: "มอบหมายนามเรียกขาน แล้วเปิดข้อความสรุปเพื่อแชร์ คัดลอก หรือส่งฉบับสั้นไปยังแอปข้อความ",
  },
  step4: {
    en: "Close the item with Done, or drop it as a duplicate or as one that could not be reached.",
    th: "ปิดรายการด้วยปุ่มเสร็จสิ้น หรือยุติรายการที่ซ้ำหรือเข้าไม่ถึง",
  },
  step5: {
    en: "Every action can be undone for 10 seconds and has a row in the exercise log. The log stays on this device.",
    th: "ทุกการดำเนินการเลิกทำได้ภายใน 10 วินาที และมีแถวในบันทึกการฝึกซ้อม ซึ่งเก็บไว้ในอุปกรณ์เครื่องนี้เท่านั้น",
  },
} as const satisfies Record<string, Localized>;
export const COMMAND_HELP_ACT_STEPS: readonly (keyof typeof COMMAND_HELP_ACT)[] = ["step1", "step2", "step3", "step4", "step5"];
