export const PUBLIC_REPORT_STORAGE_KEY = "floodguard:public-reports:v1";
export const PUBLIC_REPORT_SCHEMA_VERSION = "1.0";
export const PUBLIC_REPORT_NOTES_MAX_LENGTH = 500;
export const PUBLIC_REPORT_LIMIT = 50;

export const PUBLIC_REPORT_WATER_DEPTHS = [
  { id: "ankle", en: "Ankle", th: "ข้อเท้า" },
  { id: "knee", en: "Knee", th: "เข่า" },
  { id: "waist", en: "Waist", th: "เอว" },
  { id: "chest", en: "Chest", th: "หน้าอก" },
] as const;

export type PublicReportWaterDepth = (typeof PUBLIC_REPORT_WATER_DEPTHS)[number]["id"];

export const PUBLIC_REPORT_DEPTH_MIN_CM = 0;
export const PUBLIC_REPORT_DEPTH_MAX_CM = 150;

/**
 * Where each band ends, in centimetres, and the height it is named for. The
 * boundaries sit midway between neighbouring reference heights, so a depth
 * always lands in the band whose landmark it is closest to.
 */
export const PUBLIC_REPORT_DEPTH_BANDS = [
  { id: "ankle", referenceCm: 15, maxCm: 32 },
  { id: "knee", referenceCm: 50, maxCm: 75 },
  { id: "waist", referenceCm: 100, maxCm: 115 },
  { id: "chest", referenceCm: 130, maxCm: PUBLIC_REPORT_DEPTH_MAX_CM },
] as const;

/** Names the band a reported depth falls into. */
export function publicReportDepthBand(centimetres: number): PublicReportWaterDepth {
  for (const band of PUBLIC_REPORT_DEPTH_BANDS) {
    if (centimetres <= band.maxCm) return band.id;
  }
  return "chest";
}

function validDepthCm(value: unknown): value is number {
  return typeof value === "number"
    && Number.isFinite(value)
    && Number.isInteger(value)
    && value >= PUBLIC_REPORT_DEPTH_MIN_CM
    && value <= PUBLIC_REPORT_DEPTH_MAX_CM;
}

export interface PublicReportArea {
  area_id: string;
  area_name_th: string;
  area_name_en: string;
}

export interface PublicReport {
  schema_version: typeof PUBLIC_REPORT_SCHEMA_VERSION;
  report_id: string;
  planning_area_id: string;
  planning_area_name_th: string;
  planning_area_name_en: string;
  water_depth: PublicReportWaterDepth;
  /**
   * Depth the reader set on the slider. Optional so reports saved before the
   * slider existed still load; the band above stays the required value.
   */
  water_depth_cm?: number;
  notes: string;
  photo_attached: boolean;
  created_at: string;
  storage_scope: "device_local";
}

export interface CreatePublicReportInput {
  area: PublicReportArea;
  waterDepth: PublicReportWaterDepth;
  waterDepthCm?: number;
  notes?: string;
  photoAttached: boolean;
}

export interface PublicReportStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

const VALID_WATER_DEPTHS = new Set<string>(
  PUBLIC_REPORT_WATER_DEPTHS.map(({ id }) => id),
);

export function createPublicReport(
  input: CreatePublicReportInput,
  createdAt: string,
  reportId: string,
): PublicReport {
  if (!validArea(input.area)) {
    throw new Error("A broad planning area is required.");
  }
  if (!VALID_WATER_DEPTHS.has(input.waterDepth)) {
    throw new Error("A supported water depth is required.");
  }
  if (!validTimestamp(createdAt)) {
    throw new Error("A valid report timestamp is required.");
  }
  if (!validReportId(reportId)) {
    throw new Error("A valid device-local report ID is required.");
  }

  if (input.waterDepthCm !== undefined && !validDepthCm(input.waterDepthCm)) {
    throw new Error("A reported depth must be a whole number of centimetres in range.");
  }

  return {
    schema_version: PUBLIC_REPORT_SCHEMA_VERSION,
    report_id: reportId,
    planning_area_id: input.area.area_id.trim(),
    planning_area_name_th: input.area.area_name_th.trim(),
    planning_area_name_en: input.area.area_name_en.trim(),
    water_depth: input.waterDepth,
    ...(input.waterDepthCm === undefined ? {} : { water_depth_cm: input.waterDepthCm }),
    notes: normalizeNotes(input.notes),
    photo_attached: input.photoAttached,
    created_at: createdAt,
    storage_scope: "device_local",
  };
}

export function parseStoredPublicReports(raw: string | null): PublicReport[] {
  if (!raw) return [];

  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];

    return parsed
      .flatMap((value) => {
        const report = sanitizePublicReport(value);
        return report ? [report] : [];
      })
      .slice(0, PUBLIC_REPORT_LIMIT)
      .sort((left, right) => right.created_at.localeCompare(left.created_at));
  } catch {
    return [];
  }
}

export function readStoredPublicReports(
  storage: Pick<PublicReportStorage, "getItem"> | null,
): PublicReport[] {
  if (!storage) return [];

  try {
    return parseStoredPublicReports(storage.getItem(PUBLIC_REPORT_STORAGE_KEY));
  } catch {
    return [];
  }
}

export function writeStoredPublicReports(
  storage: Pick<PublicReportStorage, "setItem"> | null,
  reports: PublicReport[],
): void {
  if (!storage) return;

  const safeReports = reports
    .flatMap((value) => {
      const report = sanitizePublicReport(value);
      return report ? [report] : [];
    })
    .slice(0, PUBLIC_REPORT_LIMIT);

  try {
    storage.setItem(PUBLIC_REPORT_STORAGE_KEY, JSON.stringify(safeReports));
  } catch {
    // Device storage is an enhancement. Private browsing, storage quotas, or
    // browser policy must not make the report form unusable.
  }
}

export function reportsForPlanningArea(
  reports: PublicReport[],
  planningAreaId: string,
): PublicReport[] {
  if (!planningAreaId) return [];
  return reports
    .filter((report) => report.planning_area_id === planningAreaId)
    .sort((left, right) => right.created_at.localeCompare(left.created_at));
}

export function publicReportWaterDepthLabel(
  value: PublicReportWaterDepth,
  language: "th" | "en",
): string {
  return PUBLIC_REPORT_WATER_DEPTHS.find(({ id }) => id === value)?.[language] ?? value;
}

function normalizeNotes(value: string | undefined): string {
  return (value ?? "").trim().slice(0, PUBLIC_REPORT_NOTES_MAX_LENGTH);
}

function sanitizePublicReport(value: unknown): PublicReport | null {
  if (!isRecord(value)) return null;

  const valid = value.schema_version === PUBLIC_REPORT_SCHEMA_VERSION
    && validReportId(value.report_id)
    && validArea({
      area_id: value.planning_area_id,
      area_name_th: value.planning_area_name_th,
      area_name_en: value.planning_area_name_en,
    })
    && typeof value.water_depth === "string"
    && VALID_WATER_DEPTHS.has(value.water_depth)
    && typeof value.notes === "string"
    && value.notes.length <= PUBLIC_REPORT_NOTES_MAX_LENGTH
    && typeof value.photo_attached === "boolean"
    && (value.water_depth_cm === undefined || validDepthCm(value.water_depth_cm))
    && typeof value.created_at === "string"
    && validTimestamp(value.created_at)
    && value.storage_scope === "device_local";
  if (!valid) return null;

  return {
    schema_version: PUBLIC_REPORT_SCHEMA_VERSION,
    report_id: value.report_id as string,
    planning_area_id: value.planning_area_id as string,
    planning_area_name_th: value.planning_area_name_th as string,
    planning_area_name_en: value.planning_area_name_en as string,
    water_depth: value.water_depth as PublicReportWaterDepth,
    ...(value.water_depth_cm === undefined
      ? {}
      : { water_depth_cm: value.water_depth_cm as number }),
    notes: value.notes as string,
    photo_attached: value.photo_attached as boolean,
    created_at: value.created_at as string,
    storage_scope: "device_local",
  };
}

function validArea(value: unknown): value is PublicReportArea {
  if (!isRecord(value)) return false;
  return validShortText(value.area_id, 100)
    && validShortText(value.area_name_th, 160)
    && validShortText(value.area_name_en, 160);
}

function validShortText(value: unknown, maxLength: number): value is string {
  return typeof value === "string"
    && value.trim().length > 0
    && value.length <= maxLength;
}

function validReportId(value: unknown): value is string {
  return typeof value === "string"
    && /^[A-Za-z0-9][A-Za-z0-9._:-]{5,127}$/u.test(value);
}

function validTimestamp(value: string): boolean {
  return Number.isFinite(Date.parse(value));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
