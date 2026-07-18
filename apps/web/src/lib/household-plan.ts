export const HOUSEHOLD_PLAN_STORAGE_KEY = "floodguard:household-plan:v1";

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
    th: "ฝึกทางเลือกมากกว่าหนึ่งทางและยืนยันกับหน่วยงานท้องถิ่น",
    en: "Rehearse more than one option and confirm each one with local authorities",
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

export type HouseholdPlanItemId = (typeof HOUSEHOLD_PLAN_ITEMS)[number]["id"];
export type HouseholdNeedId = (typeof HOUSEHOLD_NEEDS)[number]["id"];

export interface HouseholdPlan {
  schema_version: "1.0";
  planning_area_id: string;
  checklist: Record<HouseholdPlanItemId, boolean>;
  needs: Record<HouseholdNeedId, boolean>;
  last_reviewed_at: string | null;
}

export interface HouseholdPlanStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export function createEmptyHouseholdPlan(planningAreaId: string): HouseholdPlan {
  return {
    schema_version: "1.0",
    planning_area_id: planningAreaId,
    checklist: Object.fromEntries(HOUSEHOLD_PLAN_ITEMS.map(({ id }) => [id, false])) as HouseholdPlan["checklist"],
    needs: Object.fromEntries(HOUSEHOLD_NEEDS.map(({ id }) => [id, false])) as HouseholdPlan["needs"],
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
    if (!isRecord(value) || value.schema_version !== "1.0") return fallback;

    const checklist = isRecord(value.checklist) ? value.checklist : {};
    const needs = isRecord(value.needs) ? value.needs : {};
    return {
      ...fallback,
      planning_area_id: typeof value.planning_area_id === "string" ? value.planning_area_id : fallbackAreaId,
      checklist: Object.fromEntries(
        HOUSEHOLD_PLAN_ITEMS.map(({ id }) => [id, checklist[id] === true]),
      ) as HouseholdPlan["checklist"],
      needs: Object.fromEntries(
        HOUSEHOLD_NEEDS.map(({ id }) => [id, needs[id] === true]),
      ) as HouseholdPlan["needs"],
      last_reviewed_at: validTimestamp(value.last_reviewed_at),
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
    return parseHouseholdPlan(storage.getItem(HOUSEHOLD_PLAN_STORAGE_KEY), fallbackAreaId);
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
  } catch {
    // Clearing an in-memory copy still works when browser storage is blocked.
  }
}

export function countCompletedPlanItems(plan: HouseholdPlan): number {
  return HOUSEHOLD_PLAN_ITEMS.filter(({ id }) => plan.checklist[id]).length;
}

export function buildHouseholdPlanText(
  plan: HouseholdPlan,
  areaNameTh: string,
  areaNameEn: string,
): string {
  const reviewed = plan.last_reviewed_at ?? "Not reviewed / ยังไม่ได้ทบทวน";
  const needLines = HOUSEHOLD_NEEDS.map(({ id, th, en }) => `${plan.needs[id] ? "[x]" : "[ ]"} ${th} / ${en}`);
  const itemLines = HOUSEHOLD_PLAN_ITEMS.map(({ id, th, en }) => `${plan.checklist[id] ? "[x]" : "[ ]"} ${th} / ${en}`);

  return [
    "FloodGuard household preparedness plan / แผนเตรียมพร้อมของครัวเรือน",
    "NOT AN OFFICIAL WARNING / ไม่ใช่ประกาศทางการ",
    "",
    `Planning area / พื้นที่วางแผน: ${areaNameTh || "ไม่พร้อมใช้งาน"} / ${areaNameEn || "Unavailable"}`,
    "This is a broad fixture planning area, not an exact household location.",
    "นี่เป็นพื้นที่วางแผนจากชุดข้อมูลสาธิต ไม่ใช่ตำแหน่งที่อยู่ที่แน่นอน",
    `Last reviewed / ทบทวนล่าสุด: ${reviewed}`,
    "",
    "Household planning needs / สิ่งที่ต้องคำนึงถึงในครัวเรือน",
    ...needLines,
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
