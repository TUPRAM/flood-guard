/**
 * Practice mode of the Public home map: what the September 2024 Mae Sai replay says about one home at one hour, and
 * the words the page shows for it.
 *
 * Everything here is read from the replay files as baked (revision r5): the assumed river stage of the hour, the
 * state of each road piece at that stage, the terrain height of the home, and the stage at which the home's resident
 * point loses its walk to a shelter. Nothing is added to the model. It is a T1 scenario (model) with low confidence,
 * for preparedness practice; it is not an observation of the 2024 event and it says nothing about today.
 *
 * No DOM access in this module.
 */

import {
  cellDepth,
  depthFactorScale,
  formatMoment,
  roadState,
  stageAt,
  type GeoFeature,
  type LineGeometry,
  type RoadProps,
  type TimelineManifest,
} from "./flood-timeline";
import { COMMAND_DEPTH_BAND } from "./flood-timeline-command-reports-copy";
import type { ExerciseItem } from "./flood-timeline-command-incidents";
import {
  accessLevelIndex,
  NEVER_LOST_CODE,
  NO_BASELINE_CODE,
  nodeLostAccess,
  REPORTED_SET_ID,
  type AccessNodes,
} from "./flood-timeline-evacuation";
import {
  PRACTICE_HOMES,
  PRACTICE_STATE_TONE,
  type PracticeHome,
  type PracticeScenario,
  type PracticeState,
  type PracticeTone,
} from "./public-practice-scenarios";
import type { Language } from "./types";

type Localized = Record<Language, string>;
type RoadFeature = GeoFeature<LineGeometry, RoadProps>;

/** Roads and practice reports are counted within this distance of the home (m). */
export const PRACTICE_RADIUS_M = 1000;
/** A home takes the figures of the nearest resident point of the replay when one lies within this distance (m). */
export const PRACTICE_NODE_REACH_M = 150;
/**
 * The walk to a shelter is called "close to being cut" while the river is rising and within this height (m) of the
 * stage that cuts it. One figure for every home; it is a reading aid, not a result of the model.
 */
export const REACH_RISK_MARGIN_M = 0.5;

// --- Distances -------------------------------------------------------------------------------------------

/** Ground distance (m) between two points a few kilometres apart at most (equirectangular). */
export function groundDistanceM(latitudeA: number, longitudeA: number, latitudeB: number, longitudeB: number): number {
  const metresPerDegree = 111_320;
  const east = (longitudeB - longitudeA) * metresPerDegree * Math.cos((latitudeA * Math.PI) / 180);
  const north = (latitudeB - latitudeA) * 110_540;
  return Math.hypot(east, north);
}

/** The road pieces whose middle vertex lies within `radiusM` of the point. */
export function roadsNear(roads: readonly RoadFeature[], latitude: number, longitude: number, radiusM = PRACTICE_RADIUS_M): RoadFeature[] {
  return roads.filter((road) => {
    const coordinates = road.geometry.coordinates;
    const middle = coordinates[Math.floor(coordinates.length / 2)];
    return Boolean(middle) && groundDistanceM(latitude, longitude, middle[1], middle[0]) <= radiusM;
  });
}

/** Index of the nearest resident point within `reachM` of the point, or -1. */
export function nearestAccessNode(
  nodes: Pick<AccessNodes, "count" | "lat" | "lon">,
  latitude: number,
  longitude: number,
  reachM = PRACTICE_NODE_REACH_M,
): number {
  let best = -1;
  let bestDistance = reachM;
  for (let node = 0; node < nodes.count; node += 1) {
    const distance = groundDistanceM(latitude, longitude, nodes.lat[node], nodes.lon[node]);
    if (distance <= bestDistance) {
      best = node;
      bestDistance = distance;
    }
  }
  return best;
}

// --- The state of one home at one hour -------------------------------------------------------------------

/** Length (m) of modelled road by state at one stage: passable with water on it, and impassable. */
export interface RoadTally { totalM: number; wetM: number; impassableM: number }

export function tallyRoads(roads: readonly RoadFeature[], stage: number, impassableDepthM: number): RoadTally {
  const tally: RoadTally = { totalM: 0, wetM: 0, impassableM: 0 };
  for (const { properties } of roads) {
    if (!properties.m) continue;
    tally.totalM += properties.len;
    const state = roadState(properties.h, stage, impassableDepthM, properties.k ?? 1);
    if (state === "impassable") tally.impassableM += properties.len;
    else if (state === "wet") tally.wetM += properties.len;
  }
  return tally;
}

/**
 * The walk from the home's resident point to a shelter reported in use in 2024, within the replay's threshold on
 * roads that are still passable: never within reach, within reach, within reach but close to being cut, or lost.
 */
export type PracticeReach = "none_before_flood" | "within_reach" | "at_risk" | "lost";

export interface HouseholdStatus {
  state: PracticeState;
  /** Assumed river stage of the hour (m above the mapped channel). */
  stage: number;
  rising: boolean;
  falling: boolean;
  /** Modelled depth at the home (m); null where the model is dry. */
  homeDepthM: number | null;
  reach: PracticeReach;
  /** How much higher the river must be to cut the walk (m); null when it is lost, never lost or never there. */
  reachMarginM: number | null;
  roads: RoadTally;
}

export interface HouseholdInput {
  stage: number;
  /** Stage one hour earlier and one hour later, for the direction of the water. */
  stageBefore: number;
  stageAfter: number;
  /** Terrain code and depth-factor byte of the home's resident point. */
  homeCode: number;
  homeFactor: number;
  /** Cut code of the point for the shelters reported in use in 2024 (`cut_codes` of the access node file). */
  cutCode: number;
  /** Stage levels the access was evaluated at. */
  levels: readonly number[];
  step: number;
  channelCode?: number;
  neverCode?: number;
  factorScale?: number;
  roads: RoadTally;
}

/**
 * One state per home and hour, the gravest first: water at the home; the walk to a shelter lost; that walk close to
 * being cut while the river rises; then the roads within reach (impassable, or with shallow water), which read as
 * "going down" once the river falls; else normal.
 */
export function householdStatus(input: HouseholdInput): HouseholdStatus {
  const { stage, cutCode, levels, roads } = input;
  const rising = input.stageAfter > stage + 1e-9;
  const falling = stage < input.stageBefore - 1e-9;
  const depth = cellDepth(input.homeCode, stage, input.step, input.homeFactor, input.channelCode ?? 0, input.neverCode ?? 255, input.factorScale ?? 1);
  const homeDepthM = depth !== null && depth > 0 ? depth : null;

  let reach: PracticeReach;
  let reachMarginM: number | null = null;
  if (cutCode === NO_BASELINE_CODE) reach = "none_before_flood";
  else if (nodeLostAccess(cutCode, accessLevelIndex(stage, levels))) reach = "lost";
  else if (cutCode === NEVER_LOST_CODE) reach = "within_reach";
  else {
    reachMarginM = Math.max(0, (levels[cutCode] ?? Number.POSITIVE_INFINITY) - stage);
    reach = rising && reachMarginM <= REACH_RISK_MARGIN_M ? "at_risk" : "within_reach";
  }

  let state: PracticeState;
  if (homeDepthM !== null) state = "water_at_home";
  else if (reach === "lost") state = "cut_off";
  else if (reach === "at_risk") state = "reach_at_risk";
  else if (roads.impassableM > 0) state = falling ? "going_down" : "roads_cut";
  else if (roads.wetM > 0) state = falling ? "going_down" : "heads_up";
  else state = "normal";

  return { state, stage, rising, falling, homeDepthM, reach, reachMarginM, roads };
}

/** The replay data the practice mode reads. */
export interface PracticeReplay {
  manifest: TimelineManifest;
  roads: { features: RoadFeature[] };
  nodes: AccessNodes;
}

/** The status of a home at a replay hour, or null when the home has no resident point of the replay nearby. */
export function practiceStatus(replay: PracticeReplay, home: Pick<PracticeHome, "latitude" | "longitude">, hour: number): HouseholdStatus | null {
  const { manifest, nodes } = replay;
  const access = manifest.access;
  if (!access) return null;
  const node = nearestAccessNode(nodes, home.latitude, home.longitude);
  const set = access.sets.indexOf(REPORTED_SET_ID);
  if (node < 0 || set < 0) return null;
  const stageOf = (at: number) => stageAt(at / 24, manifest.stage_anchors);
  const stage = stageOf(hour);
  return householdStatus({
    stage,
    stageBefore: stageOf(hour - 1),
    stageAfter: stageOf(hour + 1),
    homeCode: nodes.homeCode[node],
    homeFactor: nodes.homeK[node],
    cutCode: nodes.cutCodes[set * nodes.count + node],
    levels: access.levels,
    step: manifest.hand.step_m,
    channelCode: manifest.hand.channel_code,
    neverCode: manifest.hand.never_code,
    factorScale: depthFactorScale(manifest),
    roads: tallyRoads(roadsNear(replay.roads.features, home.latitude, home.longitude), stage, manifest.impassable_depth_m),
  });
}

/** The invented exercise items that have arrived by `hour`, with their distance from the home (m), nearest first. */
export function practiceReports(
  items: readonly ExerciseItem[],
  home: Pick<PracticeHome, "latitude" | "longitude">,
  hour: number,
): { item: ExerciseItem; distanceM: number }[] {
  return items
    .filter((item) => item.hour <= hour)
    .map((item) => ({ item, distanceM: groundDistanceM(home.latitude, home.longitude, item.point.lat, item.point.lon) }))
    .sort((a, b) => a.distanceM - b.distanceM);
}

// --- Words -----------------------------------------------------------------------------------------------

/** The one sentence of the banner. Short enough for two lines on a narrow phone. */
export const PRACTICE_BANNER: Readonly<Record<PracticeState, Localized>> = {
  normal: { en: "No water near this home", th: "ไม่มีน้ำท่วมใกล้บ้านนี้" },
  heads_up: { en: "Shallow water on nearby roads", th: "มีน้ำตื้นบนถนนใกล้บ้านนี้" },
  roads_cut: { en: "Nearby roads are under water", th: "ถนนใกล้บ้านนี้จมน้ำ" },
  reach_at_risk: { en: "The walk to a shelter is nearly cut", th: "ทางเดินไปที่พักพิงใกล้ถูกตัดขาด" },
  cut_off: { en: "No shelter within walking reach", th: "เดินไปที่พักพิงไม่ได้แล้ว" },
  water_at_home: { en: "Water has reached this home", th: "น้ำท่วมถึงบ้านนี้แล้ว" },
  going_down: { en: "Water is going down", th: "น้ำกำลังลดลง" },
};

/** What a household can practise in each state. A question to work through, never an instruction to move. */
export const PRACTICE_PROMPT: Readonly<Record<PracticeState, Localized>> = {
  normal: {
    en: "Practise: look at your household plan. Who would need help to move, and where would you go?",
    th: "ลองฝึก: ทบทวนแผนครัวเรือน ใครต้องการความช่วยเหลือในการเคลื่อนย้าย และจะไปที่ไหน",
  },
  heads_up: {
    en: "Practise: which roads would you use if the water kept rising, and who would you tell?",
    th: "ลองฝึก: ถ้าน้ำยังสูงขึ้น คุณจะใช้ถนนสายไหน และจะแจ้งใคร",
  },
  roads_cut: {
    en: "Practise: find a road on the map that is still passable, and decide who in the household would move first.",
    th: "ลองฝึก: หาถนนบนแผนที่ที่ยังผ่านได้ และตัดสินใจว่าใครในครัวเรือนควรออกไปก่อน",
  },
  reach_at_risk: {
    en: "Practise: decide what your household would do, leave early or stay upstairs. In a real flood, follow DDPM and call 1784.",
    th: "ลองฝึก: ตัดสินใจว่าครัวเรือนของคุณจะออกไปก่อนหรืออยู่ชั้นบน ในเหตุการณ์จริง ให้ทำตาม ปภ. และโทร 1784",
  },
  cut_off: {
    en: "Practise: stay out of the water, move what you need upstairs, and keep 1784 and 1669 at hand.",
    th: "ลองฝึก: ไม่ลงน้ำ ย้ายของจำเป็นขึ้นชั้นบน และเตรียมเบอร์ 1784 และ 1669 ไว้ใกล้มือ",
  },
  water_at_home: {
    en: "Practise: go to the highest floor you can reach with your phone and medicine, and call 1784 or 1669.",
    th: "ลองฝึก: ขึ้นไปชั้นสูงสุดที่ไปถึงได้พร้อมโทรศัพท์และยา แล้วโทร 1784 หรือ 1669",
  },
  going_down: {
    en: "Practise: check a road before you use it. Mud and damage stay after the water has gone.",
    th: "ลองฝึก: ตรวจดูถนนก่อนใช้ โคลนและความเสียหายยังอยู่หลังน้ำลด",
  },
};

/** The pages of the Public view, besides Home, that say something of their own while a scenario is shown. */
export type PracticePage = "shelter" | "report" | "prepare" | "sos";

/**
 * What a household can practise on each of those pages in each state: the same hour of the replay, seen from what
 * that page is for. Each is a question to work through. None names an hour as the time to leave, and none says
 * which place to go to.
 */
export const PRACTICE_PAGE_PROMPT: Readonly<Record<PracticePage, Readonly<Record<PracticeState, Localized>>>> = {
  shelter: {
    normal: {
      en: "Practise: which of the places on the map would you ask about first, and how would you check that it is open?",
      th: "ลองฝึก: คุณจะสอบถามสถานที่ใดบนแผนที่เป็นแห่งแรก และจะตรวจสอบอย่างไรว่าเปิดรับ",
    },
    heads_up: {
      en: "Practise: if the water kept rising, which place would you ask about, and by which road would you go?",
      th: "ลองฝึก: ถ้าน้ำยังสูงขึ้น คุณจะสอบถามสถานที่ใด และจะไปทางถนนสายไหน",
    },
    roads_cut: {
      en: "Practise: follow the roads from the example home on the map. Is there still a way on foot that keeps clear of the roads marked as under water?",
      th: "ลองฝึก: ไล่ดูถนนจากบ้านตัวอย่างบนแผนที่ ยังมีทางเดินที่ไม่ผ่านถนนที่แสดงว่าจมน้ำหรือไม่",
    },
    reach_at_risk: {
      en: "Practise: the walk to a shelter is close to being cut in the model. Who in your household decides whether to set out, and whom would they ask first?",
      th: "ลองฝึก: ในแบบจำลอง ทางเดินไปที่พักพิงใกล้ถูกตัดขาด ใครในครัวเรือนเป็นผู้ตัดสินใจว่าจะออกเดินทางหรือไม่ และจะสอบถามใครก่อน",
    },
    cut_off: {
      en: "Practise: no place is within walking reach in the model. Where in this home would you wait, and what would you tell 1784?",
      th: "ลองฝึก: ในแบบจำลอง ไม่มีสถานที่ใดอยู่ในระยะเดิน คุณจะรออยู่ที่ส่วนใดของบ้าน และจะบอก 1784 ว่าอย่างไร",
    },
    water_at_home: {
      en: "Practise: with water in the home, decide who calls 1784 or 1669 and what they say: where you are, how many people, who cannot move.",
      th: "ลองฝึก: เมื่อน้ำเข้าบ้าน ตัดสินใจว่าใครจะโทร 1784 หรือ 1669 และจะบอกอะไร: อยู่ที่ไหน มีกี่คน ใครเคลื่อนไหวไม่ได้",
    },
    going_down: {
      en: "Practise: before you go on or go back, how would you check that the road is clear of mud and damage?",
      th: "ลองฝึก: ก่อนเดินทางต่อหรือกลับบ้าน คุณจะตรวจสอบอย่างไรว่าถนนไม่มีโคลนและความเสียหาย",
    },
  },
  report: {
    normal: {
      en: "Practise: read the form on a quiet day. From where near your home could you take a photo without stepping into water?",
      th: "ลองฝึก: อ่านแบบบันทึกในวันปกติ คุณจะถ่ายภาพจากจุดใดใกล้บ้านได้โดยไม่ต้องลงน้ำ",
    },
    heads_up: {
      en: "Practise: shallow water on a road is worth a note. How deep is it against your leg, and how would you describe the place?",
      th: "ลองฝึก: น้ำตื้นบนถนนก็ควรบันทึกไว้ น้ำสูงถึงส่วนใดของขา และคุณจะบรรยายสถานที่อย่างไร",
    },
    roads_cut: {
      en: "Practise: which road near the example home is under water on the map? Describe it so that a stranger would find it.",
      th: "ลองฝึก: บนแผนที่ ถนนสายใดใกล้บ้านตัวอย่างจมน้ำ ลองบรรยายให้คนที่ไม่รู้จักพื้นที่หาเจอ",
    },
    reach_at_risk: {
      en: "Practise: what would others need to know from this home now: the depth, the road, who is with you?",
      th: "ลองฝึก: ตอนนี้ผู้อื่นควรรู้อะไรจากบ้านนี้: ความลึกของน้ำ ถนน และใครอยู่กับคุณ",
    },
    cut_off: {
      en: "Practise: what would others need to know from this home now: the depth, the road, who is with you?",
      th: "ลองฝึก: ตอนนี้ผู้อื่นควรรู้อะไรจากบ้านนี้: ความลึกของน้ำ ถนน และใครอยู่กับคุณ",
    },
    water_at_home: {
      en: "Practise: a note on this page is not a call for help. In a real flood, who needs a call first: 1784 or 1669?",
      th: "ลองฝึก: บันทึกในหน้านี้ไม่ใช่การขอความช่วยเหลือ ในเหตุการณ์จริง ควรโทรหาใครก่อน: 1784 หรือ 1669",
    },
    going_down: {
      en: "Practise: what is left that others should know of: mud, a damaged road, a blocked drain?",
      th: "ลองฝึก: ยังเหลืออะไรที่ผู้อื่นควรรู้: โคลน ถนนเสียหาย หรือท่อระบายน้ำอุดตัน",
    },
  },
  prepare: {
    normal: {
      en: "Practise: go through the checklist below on a quiet day. What is still missing?",
      th: "ลองฝึก: ทบทวนรายการด้านล่างในวันปกติ ยังขาดอะไรอยู่บ้าง",
    },
    heads_up: {
      en: "Practise: which items of the checklist would you do first today: phone, medicine, documents?",
      th: "ลองฝึก: วันนี้คุณจะทำรายการใดก่อน: โทรศัพท์ ยา หรือเอกสาร",
    },
    roads_cut: {
      en: "Practise: who in this household needs help to move, and is what they need already packed?",
      th: "ลองฝึก: ใครในครัวเรือนต้องการความช่วยเหลือในการเคลื่อนย้าย และของที่จำเป็นสำหรับเขาจัดไว้แล้วหรือยัง",
    },
    reach_at_risk: {
      en: "Practise: is the bag ready, and does everyone know where the household would meet?",
      th: "ลองฝึก: กระเป๋าพร้อมหรือยัง และทุกคนรู้หรือไม่ว่าครัวเรือนจะนัดพบกันที่ใด",
    },
    cut_off: {
      en: "Practise: what do you have upstairs for a day or more: drinking water, food, medicine, a light?",
      th: "ลองฝึก: ชั้นบนมีอะไรพอสำหรับหนึ่งวันหรือนานกว่านั้น: น้ำดื่ม อาหาร ยา และไฟฉาย",
    },
    water_at_home: {
      en: "Practise: what would you carry to the highest floor first, and what would you leave behind?",
      th: "ลองฝึก: คุณจะนำอะไรขึ้นชั้นสูงสุดเป็นอย่างแรก และจะทิ้งอะไรไว้",
    },
    going_down: {
      en: "Practise: what ran out or could not be found? Note it in your plan.",
      th: "ลองฝึก: มีอะไรหมดหรือหาไม่เจอ จดไว้ในแผนของคุณ",
    },
  },
  sos: {
    normal: {
      en: "Practise: save these numbers in your phone on a quiet day.",
      th: "ลองฝึก: บันทึกหมายเลขเหล่านี้ไว้ในโทรศัพท์ในวันปกติ",
    },
    heads_up: {
      en: "Practise: would everyone in the household know which number to call, and for what?",
      th: "ลองฝึก: ทุกคนในครัวเรือนรู้หรือไม่ว่าควรโทรหมายเลขใด และโทรเรื่องอะไร",
    },
    roads_cut: {
      en: "Practise: who outside the flooded area would you tell where you are?",
      th: "ลองฝึก: คุณจะแจ้งใครที่อยู่นอกพื้นที่น้ำท่วมว่าคุณอยู่ที่ไหน",
    },
    reach_at_risk: {
      en: "Practise: if the walk to a shelter were cut, whom would you call for help to move, and what would you say?",
      th: "ลองฝึก: ถ้าทางเดินไปที่พักพิงถูกตัดขาด คุณจะโทรขอความช่วยเหลือในการเคลื่อนย้ายจากใคร และจะพูดว่าอย่างไร",
    },
    cut_off: {
      en: "Practise: say out loud what you would tell 1784: where you are, how many people, who needs help.",
      th: "ลองฝึก: พูดออกเสียงสิ่งที่จะบอก 1784: อยู่ที่ไหน มีกี่คน ใครต้องการความช่วยเหลือ",
    },
    water_at_home: {
      en: "Practise: say out loud what you would tell 1784 or 1669: where you are, how many people, who cannot move.",
      th: "ลองฝึก: พูดออกเสียงสิ่งที่จะบอก 1784 หรือ 1669: อยู่ที่ไหน มีกี่คน ใครเคลื่อนไหวไม่ได้",
    },
    going_down: {
      en: "Practise: whom would you tell that your household is safe?",
      th: "ลองฝึก: คุณจะแจ้งใครว่าครัวเรือนของคุณปลอดภัยแล้ว",
    },
  },
};

export const PRACTICE_COPY = {
  homeLabel: { en: "Example home", th: "บ้านตัวอย่าง" },
  homeHeading: { en: "Example home in Mae Sai town", th: "บ้านตัวอย่างในตัวเมืองแม่สาย" },
  homeNote: {
    en: "Not a real address: a point of the model with residents nearby.",
    th: "ไม่ใช่ที่อยู่จริง เป็นจุดในแบบจำลองที่มีผู้อยู่อาศัยอยู่ใกล้เคียง",
  },
  noteTitle: { en: "Practice replay", th: "ฝึกซ้อมด้วยภาพจำลอง" },
  noteBoundary: {
    en: "Model · not real-time · not an official warning",
    th: "แบบจำลอง · ไม่ใช่ข้อมูลเรียลไทม์ · ไม่ใช่คำเตือนทางการ",
  },
  boundary: {
    en: "Practice replay of the September 2024 flood: a terrain model with low confidence, not a survey. Roads and shelters were not checked on the ground. Not real-time and not an official warning.",
    th: "การฝึกซ้อมด้วยภาพจำลองน้ำท่วมเดือนกันยายน 2567 (2024): เป็นแบบจำลองภูมิประเทศที่มีความเชื่อมั่นต่ำ ไม่ใช่ผลสำรวจ ถนนและที่พักพิงยังไม่ได้ตรวจในพื้นที่จริง ไม่ใช่ข้อมูลเรียลไทม์ และไม่ใช่คำเตือนทางการ",
  },
  sources: {
    en: "Sources: FloodGuard replay r5 (terrain model on the Copernicus DSM), roads and sites from OpenStreetMap, residents from WorldPop 2020.",
    th: "แหล่งข้อมูล: ภาพจำลอง FloodGuard r5 (แบบจำลองภูมิประเทศบน Copernicus DSM) ถนนและสถานที่จาก OpenStreetMap ผู้อยู่อาศัยจาก WorldPop 2020",
  },
  keyHeading: { en: "On the map", th: "บนแผนที่" },
  reportTag: { en: "Practice report, invented for the exercise. Not a real call or report.", th: "รายงานฝึกซ้อมที่สมมติขึ้นเพื่อการฝึก ไม่ใช่การโทรหรือรายงานจริง" },
  /** The Shelter page: a line drawn to a destination is the road map's and knows nothing of the replay's water. */
  routeCaveat: {
    en: "A line to a destination on this map comes from the road map. It does not know the water of the replay: compare it with the roads marked as under water.",
    th: "เส้นไปยังจุดหมายบนแผนที่นี้มาจากแผนที่ถนน และไม่ทราบน้ำในภาพจำลอง โปรดเทียบกับถนนที่แสดงว่าจมน้ำ",
  },
  /** The Report page: the invented items that have arrived by the hour shown. */
  reportsHeading: { en: "Practice reports by this hour", th: "รายงานฝึกซ้อมจนถึงชั่วโมงนี้" },
  reportsNote: {
    en: "Invented for the exercise. Not real calls or reports, and none came from this device.",
    th: "สมมติขึ้นเพื่อการฝึก ไม่ใช่การโทรหรือรายงานจริง และไม่ได้มาจากอุปกรณ์นี้",
  },
  reportsNone: { en: "No practice report has arrived by this hour.", th: "ยังไม่มีรายงานฝึกซ้อมจนถึงชั่วโมงนี้" },
  /** The SOS page: the numbers above the strip are real, the scenario is not. */
  sosReal: {
    en: "This is practice: no call is placed. In a real emergency, call the numbers above.",
    th: "นี่คือการฝึกซ้อม ไม่มีการโทรออก ในเหตุฉุกเฉินจริง ให้โทรหมายเลขด้านบน",
  },
} as const satisfies Record<string, Localized>;

/** One entry of the map key: a swatch name the stylesheet draws, and its words. */
export interface PracticeKeyItem { swatch: "water" | "peak" | "road-impassable" | "road-wet" | "report" | "radius"; text: string }

const kilometres = (metres: number): string => (Math.round(metres / 100) / 10).toFixed(1);
const centimetres = (metres: number): string => String(Math.round(metres * 100));

function roadsLine(roads: RoadTally, impassableDepthM: number, language: Language): string {
  const total = kilometres(roads.totalM);
  const impassable = kilometres(roads.impassableM);
  const wet = kilometres(roads.wetM);
  const limit = centimetres(impassableDepthM);
  const radius = kilometres(PRACTICE_RADIUS_M).replace(/\.0$/, "");
  if (roads.impassableM <= 0 && roads.wetM <= 0) {
    return language === "th"
      ? `ไม่มีน้ำบนถนนในรัศมี ${radius} กม.`
      : `No road within ${radius} km has water on it.`;
  }
  if (roads.impassableM <= 0) {
    return language === "th"
      ? `ถนน ${wet} กม. จาก ${total} กม. ในรัศมี ${radius} กม. มีน้ำตื้นไม่ถึง ${limit} ซม.`
      : `${wet} km of the ${total} km of road within ${radius} km have shallow water, under ${limit} cm.`;
  }
  return language === "th"
    ? `ถนน ${impassable} กม. จาก ${total} กม. ในรัศมี ${radius} กม. มีน้ำลึก ${limit} ซม. ขึ้นไป และอีก ${wet} กม. มีน้ำตื้นกว่านั้น`
    : `${impassable} km of the ${total} km of road within ${radius} km are under ${limit} cm of water or more. Another ${wet} km have shallower water.`;
}

function reachLine(status: HouseholdStatus, thresholdM: number, language: Language): string {
  const walk = kilometres(thresholdM).replace(/\.0$/, "");
  if (status.reach === "none_before_flood") {
    return language === "th"
      ? `ไม่มีที่พักพิงที่มีรายงานว่าเปิดใช้ในปี 2567 (2024) อยู่ในระยะเดิน ${walk} กม. จากบ้านนี้ ไม่ว่าน้ำจะท่วมหรือไม่`
      : `No shelter reported in use in 2024 is within a ${walk} km walk of this home, flood or not.`;
  }
  if (status.reach === "lost") {
    return language === "th"
      ? `เดินไปที่พักพิงที่มีรายงานว่าเปิดใช้ในปี 2567 (2024) ภายใน ${walk} กม. บนถนนที่ยังผ่านได้ไม่ได้แล้ว`
      : `No shelter reported in use in 2024 can be reached within a ${walk} km walk on passable roads.`;
  }
  if (status.reach === "at_risk" && status.reachMarginM !== null) {
    const rise = centimetres(status.reachMarginM);
    return language === "th"
      ? `ยังเดินไปที่พักพิงที่มีรายงานว่าเปิดใช้ในปี 2567 (2024) ได้ภายใน ${walk} กม. แต่ในแบบจำลอง ทางนี้ถูกตัดเมื่อระดับแม่น้ำสูงขึ้นอีกประมาณ ${rise} ซม.`
      : `A shelter reported in use in 2024 is still within a ${walk} km walk, but in the model that walk is cut once the river is about ${rise} cm higher.`;
  }
  return language === "th"
    ? `ยังเดินไปที่พักพิงที่มีรายงานว่าเปิดใช้ในปี 2567 (2024) ได้ภายใน ${walk} กม. บนถนนที่ยังผ่านได้`
    : `A shelter reported in use in 2024 is within a ${walk} km walk on passable roads.`;
}

/** The banner of the Shelter page in a scenario: whether the model still has a walk to a shelter reported in 2024. */
function shelterReachBanner(status: HouseholdStatus, thresholdM: number, language: Language): string {
  const walk = kilometres(thresholdM).replace(/\.0$/, "");
  if (status.reach === "lost") return PRACTICE_BANNER.cut_off[language];
  if (status.reach === "at_risk") return PRACTICE_BANNER.reach_at_risk[language];
  if (status.reach === "none_before_flood") {
    return language === "th"
      ? `ไม่มีที่พักพิงที่มีรายงานในปี 2567 (2024) ในระยะเดิน ${walk} กม.`
      : `No shelter reported in 2024 within a ${walk} km walk`;
  }
  return language === "th"
    ? `ยังเดินไปที่พักพิงที่มีรายงานในปี 2567 (2024) ได้ภายใน ${walk} กม.`
    : `A shelter reported in 2024 is within a ${walk} km walk`;
}

function homeLine(status: HouseholdStatus, language: Language): string {
  if (status.homeDepthM === null) {
    return language === "th" ? "ในแบบจำลอง บ้านนี้ยังไม่ถูกน้ำท่วม" : "The model has this home dry.";
  }
  const depth = (Math.round(status.homeDepthM * 10) / 10).toFixed(1);
  return language === "th"
    ? `ในแบบจำลอง น้ำที่บ้านนี้ลึกประมาณ ${depth} ม.`
    : `The model has about ${depth} m of water at this home.`;
}

function reportsLine(count: number, language: Language): string | null {
  if (count <= 0) return null;
  const radius = kilometres(PRACTICE_RADIUS_M).replace(/\.0$/, "");
  if (language === "th") return `มีรายงานฝึกซ้อม ${count} รายการในรัศมี ${radius} กม. (สมมติขึ้นเพื่อการฝึก)`;
  return count === 1
    ? `1 practice report within ${radius} km (invented for the exercise).`
    : `${count} practice reports within ${radius} km (invented for the exercise).`;
}

function keyItems(impassableDepthM: number, showPeak: boolean, hasReports: boolean, language: Language): PracticeKeyItem[] {
  const limit = centimetres(impassableDepthM);
  const radius = kilometres(PRACTICE_RADIUS_M).replace(/\.0$/, "");
  const th = language === "th";
  const items: PracticeKeyItem[] = [
    { swatch: "water", text: th ? `น้ำในภาพจำลอง: สีอ่อนตื้นกว่า ${limit} ซม. สีเข้มลึก ${limit} ซม. ขึ้นไป` : `Water in the replay: pale under ${limit} cm, dark ${limit} cm or more` },
  ];
  if (showPeak) items.push({ swatch: "peak", text: th ? "แนวที่น้ำไปถึงไกลสุดในภาพจำลอง (12 ก.ย. 2567)" : "Furthest water in the replay (12 Sep 2024)" });
  items.push(
    { swatch: "road-impassable", text: th ? `ถนนที่น้ำลึก ${limit} ซม. ขึ้นไป` : `Road under ${limit} cm of water or more` },
    { swatch: "road-wet", text: th ? "ถนนที่มีน้ำตื้นกว่านั้น" : "Road with shallower water" },
  );
  if (hasReports) items.push({ swatch: "report", text: th ? "รายงานฝึกซ้อม (EX) ที่สมมติขึ้น" : "Practice report (EX), invented" });
  items.push({ swatch: "radius", text: th ? `รัศมี ${radius} กม. รอบบ้านตัวอย่าง` : `${radius} km around the example home` });
  return items;
}

/** Short word for the depth a practice report states, for its tag on the map. */
export function practiceReportLabel(item: Pick<ExerciseItem, "depthBand">, language: Language): string {
  const words: Record<ExerciseItem["depthBand"], Localized> = {
    not_stated: { en: "report", th: "รายงาน" },
    ankle: { en: "ankle", th: "ข้อเท้า" },
    knee: { en: "knee", th: "เข่า" },
    waist: { en: "waist", th: "เอว" },
    chest: { en: "chest", th: "อก" },
    over_head: { en: "over head", th: "เกินศีรษะ" },
  };
  return words[item.depthBand][language];
}

/** The lines of a practice report's popup: the place, what the invented message says, its depth and the exercise tag. */
export function practiceReportLines(item: ExerciseItem, language: Language): { title: string; text: string; depth: string; tag: string } {
  return {
    title: item.place[language],
    text: item.text[language],
    depth: COMMAND_DEPTH_BAND[item.depthBand][language],
    tag: `${item.id} · ${PRACTICE_COPY.reportTag[language]}`,
  };
}

/** Everything the page shows for one scenario, in one language. */
export interface PracticeView {
  /**
   * What the other pages of the Public view say in this scenario: the same hour, seen from what each page is for.
   * The Shelter page has a banner and lines of its own; every page has a question to practise.
   */
  pages: {
    shelter: { banner: string; lines: string[]; prompt: string };
    report: { prompt: string; items: { id: string; title: string; text: string; depth: string }[] };
    prepare: { prompt: string };
    sos: { prompt: string };
  };
  scenario: PracticeScenario;
  home: PracticeHome;
  status: HouseholdStatus;
  tone: PracticeTone;
  /** The banner's sentence. */
  banner: string;
  /** "Thu 12 Sep 2024 · 12:00 ICT". */
  moment: string;
  /** Roads, the walk to a shelter, the home, the practice reports nearby. */
  lines: string[];
  prompt: string;
  key: PracticeKeyItem[];
  /** The invented items to draw: all that have arrived by the hour. */
  reports: ExerciseItem[];
  /** The furthest water of the replay is hatched while the water is still low. */
  showPeakExtent: boolean;
  /** The fixed words around a scenario, in the view's language. */
  copy: Record<
    "heading" | "homeLabel" | "homeNote" | "noteTitle" | "noteBoundary" | "boundary" | "sources" | "keyHeading"
    | "reportsHeading" | "reportsNote" | "reportsNone" | "sosReal",
    string
  >;
}

export function practiceView(
  replay: PracticeReplay,
  exercise: readonly ExerciseItem[],
  scenario: PracticeScenario,
  language: Language,
): PracticeView | null {
  const home = PRACTICE_HOMES[scenario.home];
  const status = practiceStatus(replay, home, scenario.hour);
  if (!status) return null;
  const { manifest } = replay;
  const arrived = practiceReports(exercise, home, scenario.hour);
  const nearby = arrived.filter((entry) => entry.distanceM <= PRACTICE_RADIUS_M).length;
  const showPeakExtent = status.state === "normal" || status.state === "heads_up";
  const thresholdM = manifest.access?.threshold_m ?? 2000;
  const roads = roadsLine(status.roads, manifest.impassable_depth_m, language);
  const reach = reachLine(status, thresholdM, language);
  const lines = [
    roads,
    reach,
    homeLine(status, language),
    reportsLine(nearby, language),
  ].filter((line): line is string => line !== null);
  return {
    pages: {
      shelter: {
        banner: shelterReachBanner(status, thresholdM, language),
        lines: [reach, roads, PRACTICE_COPY.routeCaveat[language]],
        prompt: PRACTICE_PAGE_PROMPT.shelter[status.state][language],
      },
      report: {
        prompt: PRACTICE_PAGE_PROMPT.report[status.state][language],
        items: arrived.map(({ item }) => {
          const text = practiceReportLines(item, language);
          return { id: item.id, title: text.title, text: text.text, depth: text.depth };
        }),
      },
      prepare: { prompt: PRACTICE_PAGE_PROMPT.prepare[status.state][language] },
      sos: { prompt: PRACTICE_PAGE_PROMPT.sos[status.state][language] },
    },
    scenario,
    home,
    status,
    tone: PRACTICE_STATE_TONE[status.state],
    banner: PRACTICE_BANNER[status.state][language],
    moment: formatMoment(scenario.hour / 24, language),
    lines,
    prompt: PRACTICE_PROMPT[status.state][language],
    key: keyItems(manifest.impassable_depth_m, showPeakExtent, arrived.length > 0, language),
    reports: arrived.map((entry) => entry.item),
    showPeakExtent,
    copy: {
      heading: PRACTICE_COPY.homeHeading[language],
      homeLabel: PRACTICE_COPY.homeLabel[language],
      homeNote: PRACTICE_COPY.homeNote[language],
      noteTitle: PRACTICE_COPY.noteTitle[language],
      noteBoundary: PRACTICE_COPY.noteBoundary[language],
      boundary: PRACTICE_COPY.boundary[language],
      sources: PRACTICE_COPY.sources[language],
      keyHeading: PRACTICE_COPY.keyHeading[language],
      reportsHeading: PRACTICE_COPY.reportsHeading[language],
      reportsNote: PRACTICE_COPY.reportsNote[language],
      reportsNone: PRACTICE_COPY.reportsNone[language],
      sosReal: PRACTICE_COPY.sosReal[language],
    },
  };
}
