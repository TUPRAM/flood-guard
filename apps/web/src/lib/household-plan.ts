export const HOUSEHOLD_PLAN_STORAGE_KEY = "floodguard:household-plan:v2";
export const LEGACY_HOUSEHOLD_PLAN_STORAGE_KEY = "floodguard:household-plan:v1";

export const HOUSEHOLD_PLAN_ITEMS = [
  {
    id: "official_contacts",
    th: "บันทึกหมายเลข ปภ. 1784 และการแพทย์ฉุกเฉิน 1669",
    en: "Save DDPM 1784 and medical emergency 1669",
  },
  {
    id: "waterproof_supplies",
    th: "เตรียมยา เอกสาร น้ำดื่ม และไฟฉายในถุงกันน้ำ",
    en: "Pack regular medicine, documents, drinking water, and a torch in a waterproof bag",
  },
  {
    id: "support_network",
    th: "ตกลงว่าใครจะช่วยสมาชิกครอบครัวที่ต้องการความช่วยเหลือและสัตว์เลี้ยง",
    en: "Agree who will support household members who need assistance and any pets",
  },
  {
    id: "rehearsal_options",
    th: "เตรียมทางเลือกมากกว่าหนึ่งทางและยืนยันแต่ละทางกับหน่วยงานท้องถิ่น",
    en: "Plan more than one option and confirm each one with local authorities",
  },
  {
    id: "official_updates",
    th: "ตกลงช่องทางติดตามประกาศทางการและจุดนัดพบของครอบครัว",
    en: "Agree how to follow official updates and where the household will regroup",
  },
] as const;

export const HOUSEHOLD_NEEDS = [
  { id: "children", th: "มีเด็กในครัวเรือน", en: "Children in the household" },
  { id: "older_adults", th: "มีผู้สูงอายุในครัวเรือน", en: "Older adults in the household" },
  { id: "mobility_support", th: "ต้องวางแผนความช่วยเหลือด้านการเคลื่อนไหว", en: "Mobility support needs planning" },
  { id: "regular_medicine", th: "ต้องเตรียมยาที่ใช้เป็นประจำ", en: "Regular medicine needs packing" },
  { id: "pets", th: "มีสัตว์เลี้ยง", en: "Pets in the household" },
  { id: "limited_transport", th: "ต้องประสานความช่วยเหลือด้านการเดินทาง", en: "Transport support needs coordination" },
] as const;

/**
 * Needs that describe a countable group of household members, and the words
 * used for one versus several. The rest are conditions to plan for rather than
 * people to count, so they never show a number.
 */
export const HOUSEHOLD_NEED_COUNTS: Partial<Record<HouseholdNeedId, {
  one: { en: string; th: string };
  many: { en: string; th: string };
}>> = {
  children: {
    one: { en: "child", th: "เด็ก" },
    many: { en: "children", th: "เด็ก" },
  },
  older_adults: {
    one: { en: "older adult", th: "ผู้สูงอายุ" },
    many: { en: "older adults", th: "ผู้สูงอายุ" },
  },
  pets: {
    one: { en: "pet", th: "สัตว์เลี้ยง" },
    many: { en: "pets", th: "สัตว์เลี้ยง" },
  },
};

export const HOUSEHOLD_NEED_COUNT_MAX = 20;

export function isCountableNeed(needId: HouseholdNeedId): boolean {
  return HOUSEHOLD_NEED_COUNTS[needId] !== undefined;
}

/** Renders "2 children" / "1 older adult" for countable needs. */
export function householdNeedCountLabel(
  needId: HouseholdNeedId,
  count: number,
  language: "th" | "en",
): string | undefined {
  const words = HOUSEHOLD_NEED_COUNTS[needId];
  if (!words) return undefined;
  const safe = clampNeedCount(count);
  const noun = safe === 1 ? words.one[language] : words.many[language];
  return `${safe} ${noun}`;
}

export function clampNeedCount(count: number): number {
  if (!Number.isFinite(count)) return 1;
  return Math.min(Math.max(Math.round(count), 1), HOUSEHOLD_NEED_COUNT_MAX);
}

export type HouseholdPlanItemId = (typeof HOUSEHOLD_PLAN_ITEMS)[number]["id"];
export type HouseholdNeedId = (typeof HOUSEHOLD_NEEDS)[number]["id"];
export type NeedsReviewState = "not_reviewed" | "selected" | "none_apply";

export const HOUSEHOLD_NEED_ACTIONS: Record<HouseholdNeedId, { th: string; en: string }> = {
  children: {
    th: "กำหนดผู้ดูแลเด็กและจุดนัดพบสำรองที่ทุกคนเข้าใจตรงกัน",
    en: "Name a child support person and a backup meeting place everyone understands",
  },
  older_adults: {
    th: "กำหนดผู้ช่วยผู้สูงอายุ พร้อมสำเนารายชื่อผู้ติดต่อและข้อมูลยาที่จำเป็น",
    en: "Name an older-adult support person and keep copies of essential contacts and medicine information",
  },
  mobility_support: {
    th: "ยืนยันผู้ช่วย อุปกรณ์ช่วยเคลื่อนที่ และทางเลือกการเดินทางกับหน่วยงานท้องถิ่น",
    en: "Confirm a helper, mobility equipment, and transport options with local authorities",
  },
  regular_medicine: {
    th: "เตรียมยา รายการยา ใบสั่งยา และข้อมูลผู้ให้บริการไว้ในถุงกันน้ำ",
    en: "Pack medicine, a medicine list, prescriptions, and provider details in a waterproof bag",
  },
  pets: {
    th: "ยืนยันสถานที่ที่รับสัตว์เลี้ยง เตรียมกรงหรือสายจูง อาหาร และแผนการเดินทาง",
    en: "Confirm a pet-friendly destination and prepare a carrier or lead, food, and transport plan",
  },
  limited_transport: {
    th: "บันทึกผู้ติดต่อด้านการเดินทางอย่างน้อยสองทางเลือกและยืนยันล่วงหน้า",
    en: "Record at least two transport contacts or options and confirm them in advance",
  },
};

export interface HouseholdPlan {
  schema_version: "2.0";
  planning_area_id: string;
  checklist: Record<HouseholdPlanItemId, boolean>;
  needs: Record<HouseholdNeedId, boolean>;
  /**
   * How many household members each countable need covers. Added after the 2.0
   * schema shipped, so it is filled in with 1 when a stored plan predates it
   * rather than invalidating that plan.
   */
  need_counts: Record<HouseholdNeedId, number>;
  needs_review_state: NeedsReviewState;
  needs_reviewed_at: string | null;
  last_saved_at: string | null;
  last_reviewed_at: string | null;
}

export interface HouseholdPlanStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export function createEmptyHouseholdPlan(planningAreaId: string): HouseholdPlan {
  return {
    schema_version: "2.0",
    planning_area_id: planningAreaId,
    checklist: Object.fromEntries(HOUSEHOLD_PLAN_ITEMS.map(({ id }) => [id, false])) as HouseholdPlan["checklist"],
    needs: Object.fromEntries(HOUSEHOLD_NEEDS.map(({ id }) => [id, false])) as HouseholdPlan["needs"],
    need_counts: Object.fromEntries(HOUSEHOLD_NEEDS.map(({ id }) => [id, 1])) as HouseholdPlan["need_counts"],
    needs_review_state: "not_reviewed",
    needs_reviewed_at: null,
    last_saved_at: null,
    last_reviewed_at: null,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function validTimestamp(value: unknown): string | null {
  if (typeof value !== "string" || Number.isNaN(Date.parse(value))) return null;
  return value;
}

export function parseHouseholdPlan(raw: string | null, fallbackAreaId: string): HouseholdPlan {
  const fallback = createEmptyHouseholdPlan(fallbackAreaId);
  if (!raw) return fallback;

  try {
    const value: unknown = JSON.parse(raw);
    if (!isRecord(value) || (value.schema_version !== "1.0" && value.schema_version !== "2.0")) return fallback;

    const checklist = isRecord(value.checklist) ? value.checklist : {};
    const needs = isRecord(value.needs) ? value.needs : {};
    const normalizedNeeds = Object.fromEntries(
      HOUSEHOLD_NEEDS.map(({ id }) => [id, needs[id] === true]),
    ) as HouseholdPlan["needs"];
    const hasSelectedNeeds = Object.values(normalizedNeeds).some(Boolean);
    const parsedNeedsState = value.schema_version === "2.0" && value.needs_review_state === "none_apply"
      ? "none_apply"
      : hasSelectedNeeds
        ? "selected"
        : "not_reviewed";
    const lastReviewedAt = validTimestamp(value.last_reviewed_at);
    return {
      ...fallback,
      planning_area_id: typeof value.planning_area_id === "string" ? value.planning_area_id : fallbackAreaId,
      checklist: Object.fromEntries(
        HOUSEHOLD_PLAN_ITEMS.map(({ id }) => [id, checklist[id] === true]),
      ) as HouseholdPlan["checklist"],
      needs: parsedNeedsState === "none_apply"
        ? fallback.needs
        : normalizedNeeds,
      need_counts: Object.fromEntries(HOUSEHOLD_NEEDS.map(({ id }) => {
        const stored = isRecord(value.need_counts) ? value.need_counts[id] : undefined;
        return [id, typeof stored === "number" ? clampNeedCount(stored) : 1];
      })) as HouseholdPlan["need_counts"],
      needs_review_state: parsedNeedsState,
      needs_reviewed_at: parsedNeedsState === "not_reviewed"
        ? null
        : validTimestamp(value.needs_reviewed_at) ?? (value.schema_version === "1.0" ? lastReviewedAt : null),
      last_saved_at: value.schema_version === "2.0" ? validTimestamp(value.last_saved_at) : null,
      last_reviewed_at: lastReviewedAt,
    };
  } catch {
    return fallback;
  }
}

export function readStoredHouseholdPlan(
  storage: Pick<HouseholdPlanStorage, "getItem"> | null,
  fallbackAreaId: string,
): HouseholdPlan {
  if (!storage) return createEmptyHouseholdPlan(fallbackAreaId);
  try {
    const current = storage.getItem(HOUSEHOLD_PLAN_STORAGE_KEY);
    if (current) return parseHouseholdPlan(current, fallbackAreaId);
    return parseHouseholdPlan(storage.getItem(LEGACY_HOUSEHOLD_PLAN_STORAGE_KEY), fallbackAreaId);
  } catch {
    return createEmptyHouseholdPlan(fallbackAreaId);
  }
}

export function writeStoredHouseholdPlan(
  storage: Pick<HouseholdPlanStorage, "setItem"> | null,
  plan: HouseholdPlan,
): void {
  if (!storage) return;
  try {
    storage.setItem(HOUSEHOLD_PLAN_STORAGE_KEY, JSON.stringify(plan));
  } catch {
    // Local persistence is an enhancement. Storage restrictions must not make
    // the preparedness checklist unusable during this session.
  }
}

export function removeStoredHouseholdPlan(
  storage: Pick<HouseholdPlanStorage, "removeItem"> | null,
): void {
  if (!storage) return;
  try {
    storage.removeItem(HOUSEHOLD_PLAN_STORAGE_KEY);
    storage.removeItem(LEGACY_HOUSEHOLD_PLAN_STORAGE_KEY);
  } catch {
    // Clearing an in-memory copy still works when browser storage is blocked.
  }
}

export function countCompletedPlanItems(plan: HouseholdPlan): number {
  return HOUSEHOLD_PLAN_ITEMS.filter(({ id }) => plan.checklist[id]).length;
}

export function selectedHouseholdNeeds(plan: HouseholdPlan): HouseholdNeedId[] {
  return HOUSEHOLD_NEEDS.filter(({ id }) => plan.needs[id]).map(({ id }) => id);
}

export function canReviewHouseholdPlan(plan: HouseholdPlan): boolean {
  return plan.needs_review_state !== "not_reviewed";
}

export function toggleHouseholdNeed(
  plan: HouseholdPlan,
  needId: HouseholdNeedId,
  timestamp: string,
): HouseholdPlan {
  const needs = { ...plan.needs, [needId]: !plan.needs[needId] };
  const hasSelectedNeeds = Object.values(needs).some(Boolean);
  return {
    ...plan,
    needs,
    needs_review_state: hasSelectedNeeds ? "selected" : "not_reviewed",
    needs_reviewed_at: hasSelectedNeeds ? timestamp : null,
    last_reviewed_at: null,
  };
}

export function markNoHouseholdNeedsApply(plan: HouseholdPlan, timestamp: string): HouseholdPlan {
  return {
    ...plan,
    needs: createEmptyHouseholdPlan(plan.planning_area_id).needs,
    needs_review_state: "none_apply",
    needs_reviewed_at: timestamp,
    last_reviewed_at: null,
  };
}

export function recordHouseholdPlanReview(plan: HouseholdPlan, timestamp: string): HouseholdPlan {
  return canReviewHouseholdPlan(plan) ? { ...plan, last_reviewed_at: timestamp } : plan;
}

export function buildHouseholdPlanText(
  plan: HouseholdPlan,
  areaNameTh: string,
  areaNameEn: string,
): string {
  const reviewed = plan.last_reviewed_at ?? "Not reviewed / ยังไม่ได้ทบทวน";
  const saved = plan.last_saved_at ?? "Not recorded / ไม่มีข้อมูล";
  const needLines = plan.needs_review_state === "none_apply"
    ? ["[x] None of the listed needs apply / ไม่มีข้อใดในรายการนี้ที่ใช้กับครัวเรือน"]
    : plan.needs_review_state === "not_reviewed"
      ? ["[ ] Household needs have not been reviewed / ยังไม่ได้ทบทวนความต้องการของครัวเรือน"]
      : HOUSEHOLD_NEEDS.filter(({ id }) => plan.needs[id]).map(({ th, en }) => `[x] ${th} / ${en}`);
  const tailoredActionLines = selectedHouseholdNeeds(plan).map((id) => {
    const action = HOUSEHOLD_NEED_ACTIONS[id];
    return `[ ] ${action.th} / ${action.en}`;
  });
  const itemLines = HOUSEHOLD_PLAN_ITEMS.map(({ id, th, en }) => `${plan.checklist[id] ? "[x]" : "[ ]"} ${th} / ${en}`);

  return [
    "FloodGuard household preparedness plan / แผนเตรียมพร้อมของครัวเรือน",
    "CHECK CURRENT INSTRUCTIONS WITH DDPM / ตรวจสอบคำแนะนำล่าสุดกับ ปภ.",
    "",
    `Planning area / พื้นที่วางแผน: ${areaNameTh || "ไม่พร้อมใช้งาน"} / ${areaNameEn || "Unavailable"}`,
    "This broad planning area does not identify an exact household location.",
    "พื้นที่วางแผนแบบกว้างนี้ไม่ได้ระบุตำแหน่งที่อยู่ของครัวเรือนอย่างแน่นอน",
    `Last saved / บันทึกล่าสุด: ${saved}`,
    `Last reviewed / ทบทวนล่าสุด: ${reviewed}`,
    "",
    "Household planning needs / สิ่งที่ต้องคำนึงถึงในครัวเรือน",
    ...needLines,
    "",
    "Actions for selected household needs / การดำเนินการตามความต้องการที่เลือก",
    ...(tailoredActionLines.length > 0
      ? tailoredActionLines
      : ["No tailored actions until household needs are reviewed / ยังไม่มีการดำเนินการเพิ่มเติมจนกว่าจะทบทวนความต้องการของครัวเรือน"]),
    "",
    "Preparedness checklist / รายการเตรียมพร้อม",
    ...itemLines,
    "",
    "Official help / ความช่วยเหลือทางการ: DDPM 1784; medical emergency 1669",
    "Official updates / ประกาศทางการ: https://www.disaster.go.th/home",
    "",
    "Confirm instructions and destinations with local authorities. This plan does not calculate a safe route or issue an evacuation order.",
    "ยืนยันคำแนะนำและจุดหมายกับหน่วยงานท้องถิ่น แผนนี้ไม่คำนวณเส้นทางปลอดภัยและไม่ออกคำสั่งอพยพ",
  ].join("\n");
}
