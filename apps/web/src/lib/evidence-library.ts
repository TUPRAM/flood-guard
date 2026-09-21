import { EVIDENCE_AVAILABILITIES } from "@floodguard/contracts";
import type { EvidenceLibraryCatalog, EvidenceLibraryGauge, EvidenceLibraryPackage, EvidencePackageReference } from "@floodguard/contracts";

export const EVIDENCE_CATALOG_URL = "/evidence-library/catalog.json";
const digestPattern = /^[a-f0-9]{64}$/;

/** Static exports can load only explicitly named files inside the evidence directory. */
export function evidenceAssetUrl(value: unknown): string | null {
  return typeof value === "string" && /^\/evidence-library\/[A-Za-z0-9_/-]+\.(?:json(?:\.gz)?|geojson|md|html|txt|csv|pdf|png|webp)$/.test(value)
    && !value.includes("..") && !value.includes("//") ? value : null;
}

function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function strings(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}
function rows(value: unknown): value is Record<string, unknown>[] {
  return Array.isArray(value) && value.every(object);
}
function text(value: unknown): value is string { return typeof value === "string" && value.length > 0; }
function nullableText(value: unknown): boolean { return value === null || typeof value === "string"; }
function available(value: unknown): boolean { return EVIDENCE_AVAILABILITIES.includes(value as never); }
function uniqueIds(value: Record<string, unknown>[]): boolean {
  return value.every((item) => text(item.id)) && new Set(value.map((item) => item.id)).size === value.length;
}
function sourceUrl(value: string): boolean {
  try { return ["https:", "http:"].includes(new URL(value).protocol); } catch { return false; }
}

export function parseEvidenceCatalog(value: unknown): EvidenceLibraryCatalog {
  if (!object(value) || value.schema_version !== "1.0" || value.non_operational !== true
    || !text(value.generated_at) || !text(value.package_version)
    || !rows(value.aois) || !rows(value.events) || !rows(value.datasets) || !rows(value.packages)) {
    throw new Error("Invalid candidate evidence catalog.");
  }
  for (const list of [value.aois, value.events, value.datasets, value.packages]) {
    if (!uniqueIds(list)) throw new Error("Duplicate or missing evidence identifiers.");
  }
  if (!value.aois.every((aoi) => text(aoi.name) && object(aoi.geometry) && text(aoi.geometry.type)
    && (aoi.sha256 === undefined || (typeof aoi.sha256 === "string" && digestPattern.test(aoi.sha256)))
    && strings(aoi.event_ids) && aoi.event_ids.every((id) => (value.events as Record<string, unknown>[]).some((event) => event.id === id)))
    || !value.events.every((event) => text(event.name) && text(event.start) && text(event.end))
    || !value.datasets.every((dataset) => text(dataset.title) && text(dataset.role)
      && strings(dataset.source_urls) && dataset.source_urls.every(sourceUrl) && strings(dataset.limitations)
      && object(dataset.temporal) && nullableText(dataset.temporal.start) && nullableText(dataset.temporal.end)
      && text(dataset.temporal.kind) && text(dataset.temporal.label)
      && object(dataset.rights) && text(dataset.rights.status) && nullableText(dataset.rights.license)
      && typeof dataset.rights.public_derivatives === "boolean" && strings(dataset.rights.attribution))) {
    throw new Error("Incomplete evidence source metadata.");
  }
  const catalog = value as unknown as EvidenceLibraryCatalog;
  const pairs = new Set<string>();
  for (const reference of catalog.packages) {
    const pair = `${reference.aoi_id}/${reference.event_id}`;
    if (!catalog.aois.some((aoi) => aoi.id === reference.aoi_id && aoi.event_ids.includes(reference.event_id))
      || !evidenceAssetUrl(reference.url) || !digestPattern.test(reference.sha256) || pairs.has(pair)) {
      throw new Error("Invalid or duplicate AOI/event package binding.");
    }
    pairs.add(pair);
  }
  return catalog;
}

/** Unknown AOI/event pairs stay unavailable; never borrow another area's package. */
export function selectEvidencePackage(catalog: EvidenceLibraryCatalog, aoiId: string, eventId: string): EvidencePackageReference | null {
  return catalog.packages.find((item) => item.aoi_id === aoiId && item.event_id === eventId) ?? null;
}

export function parseEvidencePackage(value: unknown, catalog: EvidenceLibraryCatalog, reference: EvidencePackageReference): EvidenceLibraryPackage {
  if (!object(value) || value.schema_version !== "1.0" || value.package_version !== catalog.package_version || value.id !== reference.id
    || value.aoi_id !== reference.aoi_id || value.event_id !== reference.event_id
    || value.dataset_mode !== "candidate" || value.official_warning !== false || value.operational_status !== "non_operational"
    || value.confidence_class !== "low" || !strings(value.assumptions) || !nullableText(value.source_timestamp)
    || !text(value.generated_at) || !object(value.input_hashes) || !Object.values(value.input_hashes).every((hash) => typeof hash === "string" && digestPattern.test(hash))
    || !rows(value.datasets) || !rows(value.layers) || !rows(value.gauges) || !rows(value.scenarios)
    || !object(value.assessment) || (value.report_url !== null && !evidenceAssetUrl(value.report_url))) {
    throw new Error("Evidence package identity, provenance or safety boundary is invalid.");
  }
  const aoiHash = catalog.aois.find((item) => item.id === reference.aoi_id)?.sha256;
  if (aoiHash && value.input_hashes.aoi_sha256 !== aoiHash) throw new Error("Evidence package AOI checksum differs from the catalog.");
  if (value.downloads !== undefined && (!rows(value.downloads) || !value.downloads.every((item) => text(item.title)
    && evidenceAssetUrl(item.url) && typeof item.sha256 === "string" && digestPattern.test(item.sha256)))) {
    throw new Error("Invalid evidence download binding.");
  }
  if (!value.datasets.every((row) => catalog.datasets.some((dataset) => dataset.id === row.dataset_id)
    && available(row.availability) && typeof row.coverage === "string" && strings(row.qc) && typeof row.summary === "string")) {
    throw new Error("Invalid source availability record.");
  }
  for (const layer of value.layers) {
    const source = catalog.datasets.find((dataset) => dataset.id === layer.dataset_id);
    if (!source || !text(layer.id) || !text(layer.title) || !text(layer.role) || !available(layer.availability) || !nullableText(layer.reason)
      || (layer.data !== undefined && (!source.rights.public_derivatives || !["available", "partial"].includes(String(layer.availability))
        || !object(layer.data) || layer.data.type !== "FeatureCollection" || !rows(layer.data.features)))) {
      throw new Error("A map layer is malformed or lacks derivative publication clearance.");
    }
    if (layer.image_url !== undefined && (!source.rights.public_derivatives || !["available", "partial"].includes(String(layer.availability))
      || !evidenceAssetUrl(layer.image_url) || !/\.(png|webp)$/.test(String(layer.image_url))
      || !Array.isArray(layer.bounds) || layer.bounds.length !== 2
      || !layer.bounds.every((corner) => Array.isArray(corner) && corner.length === 2 && corner.every((coordinate) => typeof coordinate === "number" && Number.isFinite(coordinate)))
      || !text(layer.attribution))) {
      throw new Error("Invalid or uncleared terrain preview.");
    }
  }
  if (!value.gauges.every((gauge) => text(gauge.id) && text(gauge.name) && text(gauge.units) && nullableText(gauge.timezone)
    && strings(gauge.limitations) && rows(gauge.points) && gauge.points.every((point) => text(point.time)
      && Number.isFinite(sourceClockCoordinate(point.time, typeof gauge.timezone === "string" ? gauge.timezone : null))
      && (point.value === null || (typeof point.value === "number" && Number.isFinite(point.value)))))) {
    throw new Error("Invalid gauge observations.");
  }
  const assessment = value.assessment;
  if (assessment.fpps !== null || assessment.action_class !== null || !strings(assessment.limitations) || !rows(assessment.components)
    || !assessment.components.every((component) => text(component.id) && text(component.label)
      && typeof component.weight === "number" && component.weight >= 0 && component.weight <= 1 && nullableText(component.reason)
      && (component.value === null || (typeof component.value === "number" && component.value >= 0 && component.value <= 100)))
    || (assessment.bounds !== null && (!object(assessment.bounds) || typeof assessment.bounds.lower !== "number"
      || typeof assessment.bounds.upper !== "number" || !Number.isFinite(assessment.bounds.lower) || !Number.isFinite(assessment.bounds.upper)
      || assessment.bounds.lower < 0 || assessment.bounds.upper > 100 || assessment.bounds.lower > assessment.bounds.upper))) {
    throw new Error("Invalid partial assessment; a candidate package cannot publish an action class or complete FPPS.");
  }
  if (!value.scenarios.every((scenario) => text(scenario.id) && text(scenario.title) && text(scenario.kind)
    && typeof scenario.summary === "string" && strings(scenario.assumptions) && rows(scenario.metrics)
    && scenario.metrics.every((metric) => text(metric.label) && (metric.value === null || typeof metric.value === "string"
      || (typeof metric.value === "number" && Number.isFinite(metric.value))) && (metric.unit === undefined || typeof metric.unit === "string")))) {
    throw new Error("Invalid scenario summary.");
  }
  return value as unknown as EvidenceLibraryPackage;
}

export async function fetchEvidencePackage(catalog: EvidenceLibraryCatalog, reference: EvidencePackageReference, signal?: AbortSignal): Promise<EvidenceLibraryPackage> {
  const url = evidenceAssetUrl(reference.url);
  if (!url) throw new Error("Invalid evidence asset URL.");
  const response = await fetch(url, { signal });
  if (!response.ok) throw new Error(`Evidence package unavailable (${response.status}).`);
  const bytes = await response.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  const actual = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
  if (actual !== reference.sha256) throw new Error("Evidence package checksum does not match the catalog.");
  return parseEvidencePackage(JSON.parse(new TextDecoder().decode(bytes)), catalog, reference);
}

/**
 * Map a naive source clock onto an abstract, timezone-independent plotting axis.
 * Date.UTC supplies calendar arithmetic only: its result is not an assertion
 * that an unconfirmed source observation occurred in UTC. Explicit offsets are
 * accepted only when the series also records a confirmed timezone.
 */
export function sourceClockCoordinate(time: string, timezone: string | null = null): number {
  const parts = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,9}))?)?(Z|[+-]\d{2}:\d{2})?$/.exec(time);
  if (!parts) return Number.NaN;
  const [, yearText, monthText, dayText, hourText, minuteText, secondText = "0", fraction = "", offset] = parts;
  const [year, month, day, hour, minute, second] = [yearText, monthText, dayText, hourText, minuteText, secondText].map(Number);
  const millisecond = Number(fraction.slice(0, 3).padEnd(3, "0"));
  const axis = new Date(Date.UTC(year, month - 1, day, hour, minute, second, millisecond));
  if (year < 100) axis.setUTCFullYear(year);
  if (axis.getUTCFullYear() !== year || axis.getUTCMonth() !== month - 1 || axis.getUTCDate() !== day
    || axis.getUTCHours() !== hour || axis.getUTCMinutes() !== minute || axis.getUTCSeconds() !== second) return Number.NaN;
  if (offset) {
    if (!timezone?.trim() || /unknown|unconfirmed/i.test(timezone)) return Number.NaN;
    return Date.parse(time.replace(" ", "T"));
  }
  return axis.getTime();
}

/** Missing observations and absent ten-minute slots break the line instead of implying continuity. */
export function gaugeSegments(points: EvidenceLibraryGauge["points"], maximumGapMs = 10 * 60 * 1000, timezone: string | null = null): EvidenceLibraryGauge["points"][] {
  const segments: EvidenceLibraryGauge["points"][] = [];
  let current: EvidenceLibraryGauge["points"] = [];
  let previous: number | null = null;
  for (const point of points) {
    const time = sourceClockCoordinate(point.time, timezone);
    if (point.value === null || !Number.isFinite(time) || !Number.isFinite(point.value)) {
      if (current.length) segments.push(current);
      current = []; previous = null;
      continue;
    }
    if (previous !== null && (time <= previous || time - previous > maximumGapMs)) {
      if (current.length) segments.push(current);
      current = [];
    }
    current.push(point); previous = time;
  }
  if (current.length) segments.push(current);
  return segments;
}
