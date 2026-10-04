import { createHash } from "node:crypto";
import { existsSync, lstatSync, mkdtempSync, readFileSync, readdirSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { basename, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";
import { assertPublicEvidenceText } from "./evidence-library-assets.mjs";
import { collectPublicCaseAssets } from "./public-case-assets.mjs";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const defaultPublicDirectory = resolve(scriptDirectory, "..", "public");
const SHA256 = /^[a-f0-9]{64}$/;
const ID = /^[a-z0-9][a-z0-9_.-]{0,100}$/;
const CASE_KEYS = [
  "access", "action_class", "affected_population", "aoi_id", "confidence_class", "dataset_mode",
  "demographic_equity_status", "event_id", "fpps", "generated_at", "id", "limitations",
  "official_warning", "operational_status", "package_version", "population_reference_year", "population_role",
  "reporting_coverage_fraction", "reporting_scope", "schema_version", "services", "source_package_sha256",
  "source_analysis_generated_at", "source_timestamp",
];
const SERVICE_KEYS = ["facilities", "id", "reason", "status", "variants"];
const VARIANT_KEYS = [
  "candidate_flood_losing_30_min_access", "candidate_flood_newly_unreachable_population",
  "candidate_flood_scenario_id", "candidate_flood_source_timestamp", "connected_without_route_population",
  "id", "modelled_population", "travel_mode", "unknown_access_population", "within_30_minutes_population",
];
const ACCESS_KEYS = ["connected_without_route_population", "modelled_population", "unknown_access_population", "within_30_minutes_population"];
const BASE_RIGHTS = ["context-worldpop", "context-osm", "context-admin", "project-scenarios"];
const SOURCE_LABELS = [
  "WorldPop modelled residential population", "OpenStreetMap candidate roads and destinations",
  "Royal Thai Survey Department / OCHA COD-AB reporting boundaries",
];

const sha256 = (value) => createHash("sha256").update(value).digest("hex");
const jsonBytes = (value) => Buffer.from(`${JSON.stringify(value)}\n`, "utf8");
const isPlainObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const assert = (condition, message) => { if (!condition) throw new Error(message); };

function exactKeys(value, keys, label) {
  assert(isPlainObject(value), `${label} must be an object`);
  assert(JSON.stringify(Object.keys(value).sort()) === JSON.stringify([...keys].sort()), `${label} has unapproved fields`);
}

function finiteNonnegative(value, label, nullable = false) {
  if (nullable && value === null) return;
  assert(typeof value === "number" && Number.isFinite(value) && value >= 0, `${label} must be a finite nonnegative number`);
}

function text(value, label, nullable = false) {
  if (nullable && value === null) return;
  assert(typeof value === "string" && value.length > 0 && value.length <= 500, `${label} is missing or invalid`);
  assertPublicEvidenceText(value);
}

function safeRead(path, label) {
  assert(existsSync(path) && lstatSync(path).isFile() && !lstatSync(path).isSymbolicLink(), `${label} is missing or linked`);
  return readFileSync(path);
}

export function validateBriefCase(value, reference, version) {
  exactKeys(value, CASE_KEYS, `case ${reference.id}`);
  assert(value.schema_version === "floodguard.public_case.v1" && value.package_version === version
    && value.id === reference.id && value.aoi_id === reference.aoi_id && value.event_id === reference.event_id
    && value.source_package_sha256 === reference.source_package_sha256, `Case identity mismatch: ${reference.id}`);
  assert(value.dataset_mode === "candidate" && value.operational_status === "non_operational"
    && value.official_warning === false && value.confidence_class === "low"
    && value.fpps === null && value.action_class === null && value.affected_population === null
    && value.demographic_equity_status === "unavailable", `Accepted-looking case fields: ${reference.id}`);
  assert(value.population_role === "modelled_residential_context", `Unrecognized population role: ${reference.id}`);
  text(value.generated_at, "generated_at");
  text(value.source_analysis_generated_at, "source_analysis_generated_at", true);
  assert(value.source_analysis_generated_at === null || (Number.isFinite(Date.parse(value.source_analysis_generated_at))
    && Number.isFinite(Date.parse(value.generated_at)) && Date.parse(value.source_analysis_generated_at) <= Date.parse(value.generated_at)),
  `Source analysis time exceeds package release: ${reference.id}`);
  text(value.source_timestamp, "source_timestamp", true);
  text(value.reporting_scope, "reporting_scope");
  finiteNonnegative(value.reporting_coverage_fraction, "reporting_coverage_fraction");
  assert(value.reporting_coverage_fraction <= 1, "Reporting coverage exceeds one");
  assert(value.population_reference_year === null || (Number.isInteger(value.population_reference_year)
    && value.population_reference_year >= 1900 && value.population_reference_year <= 2100), "Invalid population year");
  assert(value.access === null, `Generic mixed-basis access must be omitted: ${reference.id}`);
  assert(Array.isArray(value.limitations) && value.limitations.length >= 3, `Missing limitations: ${reference.id}`);
  for (const limitation of value.limitations) text(limitation, "limitation");
  assert(Array.isArray(value.services), `Missing services: ${reference.id}`);
  const services = new Set();
  for (const service of value.services) {
    exactKeys(service, SERVICE_KEYS, `service in ${reference.id}`);
    assert(["hospital", "primary_care", "pharmacy", "shelter", "main_road"].includes(service.id)
      && !services.has(service.id), `Unknown or duplicate service: ${reference.id}`);
    services.add(service.id);
    assert(["available", "unavailable"].includes(service.status), `Unknown service status: ${reference.id}`);
    text(service.reason, "service reason", true);
    finiteNonnegative(service.facilities, "facilities", true);
    assert(Array.isArray(service.variants), `Invalid service variants: ${reference.id}`);
    if (service.id === "main_road") assert(service.status === "unavailable" && service.reason !== null && service.facilities === null
      && service.variants.length === 0, `Unqualified main-road access cannot carry numeric results: ${reference.id}`);
    const modes = new Set();
    for (const variant of service.variants) {
      exactKeys(variant, VARIANT_KEYS, `variant in ${reference.id}`);
      assert(["walking", "modelled_vehicle"].includes(variant.travel_mode)
        && variant.id === `${service.id}-${variant.travel_mode}-1` && !modes.has(variant.travel_mode),
      `Unknown or duplicate service variant: ${reference.id}`);
      modes.add(variant.travel_mode);
      for (const key of ACCESS_KEYS) finiteNonnegative(variant[key], key);
      assert(variant.within_30_minutes_population + variant.connected_without_route_population
        + variant.unknown_access_population <= variant.modelled_population + 0.1,
      `Service variant population accounting exceeds denominator: ${reference.id}`);
      const scenarioPresent = variant.candidate_flood_scenario_id !== null;
      assert(scenarioPresent === (variant.candidate_flood_losing_30_min_access !== null)
        && scenarioPresent === (variant.candidate_flood_newly_unreachable_population !== null),
      `Partial scenario fields: ${reference.id}`);
      if (scenarioPresent) {
        assert(variant.candidate_flood_scenario_id === "candidate-flood-closure", `Unknown scenario: ${reference.id}`);
        finiteNonnegative(variant.candidate_flood_losing_30_min_access, "candidate loss");
        finiteNonnegative(variant.candidate_flood_newly_unreachable_population, "candidate newly unreachable");
        assert(variant.candidate_flood_losing_30_min_access <= variant.within_30_minutes_population + 0.1,
          `Candidate threshold loss exceeds baseline: ${reference.id}`);
      }
      text(variant.candidate_flood_source_timestamp, "candidate flood source time", true);
    }
    if (service.status === "unavailable") assert(service.variants.length === 0, `Unavailable service has variants: ${reference.id}`);
  }
  assert(services.has("main_road"), `Explicit unavailable main-road category is missing: ${reference.id}`);
}

export function assertBriefRights(sourceCatalog, projected) {
  assert(Array.isArray(sourceCatalog.datasets), "Source rights catalog is missing datasets");
  const rights = new Map(sourceCatalog.datasets.map((item) => [item.id, item.rights?.public_derivatives]));
  for (const source of BASE_RIGHTS) assert(rights.get(source) === true, `Download derivative permission missing: ${source}`);
  if (projected.services.some((service) => service.variants.some((variant) => variant.candidate_flood_scenario_id !== null))) {
    assert(rights.get("context-sar-candidate") === true, `Candidate flood derivative permission missing: ${projected.id}`);
  }
}

export function assertBriefTimeBinding(projected, sourcePackage, caseId) {
  const sourceAnalysisTime = sourcePackage.decision_brief?.finals_analysis?.generated_at ?? null;
  assert(sourcePackage.decision_brief?.generated_at === sourcePackage.generated_at
    && projected.generated_at === sourcePackage.generated_at
    && projected.source_analysis_generated_at === sourceAnalysisTime,
  `Source analysis/release time binding mismatch: ${caseId}`);
  if (sourceAnalysisTime !== null && sourceAnalysisTime !== sourcePackage.generated_at) {
    assert(SHA256.test(sourcePackage.input_hashes?.finals_receipt_sha256 ?? "")
      && SHA256.test(sourcePackage.input_hashes?.finals_generation_identity_sha256 ?? ""),
    `Mixed-time analysis lacks source identity receipts: ${caseId}`);
  }
}

export function loadBriefSource(publicDirectory = defaultPublicDirectory, expectedCatalogSha256) {
  assert(SHA256.test(expectedCatalogSha256 ?? ""), "Pinned projection catalog SHA-256 is required");
  collectPublicCaseAssets(publicDirectory);
  const projectionCatalogBytes = safeRead(resolve(publicDirectory, "public-case-projections", "catalog.json"), "projection catalog");
  assert(sha256(projectionCatalogBytes) === expectedCatalogSha256, "Projection catalog SHA-256 mismatch");
  const catalog = JSON.parse(projectionCatalogBytes.toString("utf8"));
  exactKeys(catalog, ["aois", "events", "package_version", "packages", "schema_version", "source_catalog_sha256"], "projection catalog");
  assert(catalog.schema_version === "floodguard.public_case_catalog.v1" && SHA256.test(catalog.source_catalog_sha256), "Invalid projection catalog version");
  assert(Array.isArray(catalog.aois) && Array.isArray(catalog.events) && Array.isArray(catalog.packages) && catalog.packages.length > 0,
    "Projection catalog lists no cases");
  const sourceCatalog = JSON.parse(safeRead(resolve(publicDirectory, "evidence-library", "catalog.json"), "source catalog").toString("utf8"));
  assert(sourceCatalog.schema_version === "1.0" && sourceCatalog.non_operational === true
    && sourceCatalog.package_version === catalog.package_version && Array.isArray(sourceCatalog.packages)
    && Array.isArray(sourceCatalog.datasets), "Source catalog is not the matching non-operational release");
  const cases = [];
  const seen = new Set();
  for (const reference of catalog.packages) {
    exactKeys(reference, ["aoi_id", "event_id", "id", "sha256", "source_package_sha256", "url"], "case reference");
    assert(ID.test(reference.id) && ID.test(reference.aoi_id) && ID.test(reference.event_id)
      && SHA256.test(reference.sha256) && SHA256.test(reference.source_package_sha256)
      && reference.url === `/public-case-projections/cases/${reference.id}.json`
      && !seen.has(reference.id), "Unsafe or duplicate case reference");
    seen.add(reference.id);
    const aoi = catalog.aois.find((item) => item.id === reference.aoi_id);
    const event = catalog.events.find((item) => item.id === reference.event_id);
    assert(aoi && event, `Missing case labels: ${reference.id}`);
    const sourceRef = sourceCatalog.packages.find((item) => item.id === reference.id
      && item.aoi_id === reference.aoi_id && item.event_id === reference.event_id);
    assert(sourceRef?.sha256 === reference.source_package_sha256
      && sourceRef.url === `/evidence-library/packages/${reference.id}.json`, `Source package reference mismatch: ${reference.id}`);
    const sourceBytes = safeRead(resolve(publicDirectory, sourceRef.url.slice(1)), `source package ${reference.id}`);
    assert(sha256(sourceBytes) === reference.source_package_sha256, `Source package SHA-256 mismatch: ${reference.id}`);
    const sourcePackage = JSON.parse(sourceBytes.toString("utf8"));
    assert(sourcePackage.id === reference.id && sourcePackage.aoi_id === reference.aoi_id
      && sourcePackage.event_id === reference.event_id && sourcePackage.package_version === catalog.package_version
      && sourcePackage.dataset_mode === "candidate" && sourcePackage.operational_status === "non_operational"
      && sourcePackage.official_warning === false && sourcePackage.assessment?.fpps === null
      && sourcePackage.assessment?.action_class === null && sourcePackage.decision_brief?.affected_population === null,
    `Source package is not an unaccepted candidate: ${reference.id}`);
    text(aoi.name, "AOI English name"); text(aoi.name_th, "AOI Thai name");
    text(event.name, "event English name"); text(event.name_th, "event Thai name");
    text(event.start, "event start"); text(event.end, "event end");
    const projected = JSON.parse(safeRead(resolve(publicDirectory, reference.url.slice(1)), `projection ${reference.id}`).toString("utf8"));
    validateBriefCase(projected, reference, catalog.package_version);
    assertBriefTimeBinding(projected, sourcePackage, reference.id);
    assertBriefRights(sourceCatalog, projected);
    cases.push({ reference, aoi, event, projected });
  }
  return { catalog, catalogSha256: expectedCatalogSha256, cases };
}

const escapeHtml = (value) => String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;");
const whole = (value) => new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(Math.round(value));
const pct = (value) => new Intl.NumberFormat("en-US", { maximumFractionDigits: 1, minimumFractionDigits: 1 }).format(value * 100);

function messageRows({ projected, event }) {
  const lowerBasin = projected.aoi_id.startsWith("aoi-05") || projected.aoi_id.startsWith("aoi-06");
  const hospital = projected.services.find((service) => service.id === "hospital" && service.status === "available");
  const illustration = hospital?.variants.find((variant) => variant.travel_mode === "walking") ?? null;
  const scenario = illustration?.candidate_flood_scenario_id ? illustration : null;
  const coverage = pct(projected.reporting_coverage_fraction);
  const denominatorEn = illustration
    ? `Hospital / walking illustration: about ${whole(illustration.modelled_population)} modelled residents (${projected.population_reference_year} source). Reporting geometry covers ${coverage}% of the study AOI. Counts concern AOI intersections, not whole subdistricts or observed victims.`
    : `A modelled population and service-access denominator is unavailable for this case. Reporting geometry covers ${coverage}% of the study AOI; this is not a whole-subdistrict or event-casualty count.`;
  const denominatorTh = illustration
    ? `ตัวอย่างโรงพยาบาล / การเดิน: ประชากรที่ประมาณด้วยแบบจำลองราว ${whole(illustration.modelled_population)} คน (ข้อมูลปี ${projected.population_reference_year}) พื้นที่รายงานครอบคลุม ${coverage}% ของพื้นที่ศึกษา ตัวเลขเป็นส่วนที่ตัดกับพื้นที่ศึกษา ไม่ใช่ทั้งตำบลหรือผู้ประสบภัยที่สังเกตได้`
    : `กรณีนี้ยังไม่มีตัวหารประชากรและผลการเข้าถึงบริการจากแบบจำลอง พื้นที่รายงานครอบคลุม ${coverage}% ของพื้นที่ศึกษา ไม่ใช่จำนวนทั้งตำบลหรือผู้ประสบภัยที่สังเกตได้`;
  const accessEn = illustration
    ? `In the baseline model, about ${whole(illustration.within_30_minutes_population)} residents are within 30 minutes of a candidate hospital on foot; ${whole(illustration.unknown_access_population)} have unknown access and ${whole(illustration.connected_without_route_population)} have no route to this service. These categories use the hospital / walking denominator above.`
    : "No eligible service/mode comparison is available here. Missing access is unknown, not zero.";
  const accessTh = illustration
    ? `ในแบบจำลองฐาน ประชากรราว ${whole(illustration.within_30_minutes_population)} คนอยู่ภายใน 30 นาทีเมื่อเดินไปยังโรงพยาบาลที่ยังเป็นจุดบริการเบื้องต้น; ${whole(illustration.unknown_access_population)} คนมีสถานะการเข้าถึงไม่ทราบ และ ${whole(illustration.connected_without_route_population)} คนไม่มีเส้นทางไปบริการนี้ โดยใช้ตัวหารโรงพยาบาล / การเดินข้างต้น`
    : "กรณีนี้ยังไม่มีผลเปรียบเทียบบริการและวิธีเดินทางที่เข้าเกณฑ์ ข้อมูลการเข้าถึงที่ขาดไปคือไม่ทราบ ไม่ใช่ศูนย์";
  const scenarioEn = scenario
    ? `If the precomputed candidate closure is imposed, about ${whole(scenario.candidate_flood_losing_30_min_access)} residents lose 30-minute hospital access and ${whole(scenario.candidate_flood_newly_unreachable_population)} become newly unreachable in this model. The road closure is an assumption, not an observed closure.`
    : `No eligible flood-disruption comparison is published for this case. Do not infer an observed closure or zero impact.${lowerBasin ? " The 2024 and 2025 selections share one static access baseline; routing uses a 10 km AOI buffer while resident demand and reporting stay in AOI intersections. This is not a year-on-year flood comparison." : ""}`;
  const scenarioTh = scenario
    ? `หากกำหนดให้ถนนปิดตามฉากทัศน์ที่คำนวณไว้ ประชากรราว ${whole(scenario.candidate_flood_losing_30_min_access)} คนจะเสียการเข้าถึงโรงพยาบาลภายใน 30 นาที และ ${whole(scenario.candidate_flood_newly_unreachable_population)} คนจะเข้าถึงไม่ได้เพิ่มขึ้นในแบบจำลอง การปิดถนนเป็นสมมติฐาน ไม่ใช่การปิดที่สังเกตได้`
    : `กรณีนี้ยังไม่มีผลเปรียบเทียบการหยุดชะงักจากน้ำท่วมที่เผยแพร่ ห้ามตีความว่าเป็นการปิดถนนที่สังเกตได้หรือผลกระทบเป็นศูนย์${lowerBasin ? " ตัวเลือกปี 2024 และ 2025 ใช้กรณีฐานการเข้าถึงแบบคงที่เดียวกัน การหาเส้นทางใช้พื้นที่กันชน 10 กม. รอบ AOI ส่วนประชากรและพื้นที่รายงานยังอยู่ในส่วนตัดกับ AOI ไม่ใช่การเปรียบเทียบผลน้ำท่วมรายปี" : ""}`;
  const taskEn = scenario
    ? "Check the consequential candidate road links, crossing and hospital entrance/operation against dated local evidence; then compare a plausible open-link alternative before using this for a decision."
    : illustration
      ? "Review road connectivity, candidate hospital identity and entrance/operation; establish an event-matched flood footprint before comparing disruption."
      : "Qualify the residential surface, road graph and eligible destinations for this AOI; establish an event-matched flood footprint before estimating disruption.";
  const taskTh = scenario
    ? "ตรวจสอบถนน จุดข้าม และทางเข้า/การเปิดบริการของโรงพยาบาลที่ส่งผลมากด้วยหลักฐานท้องถิ่นตามวันเวลา แล้วเปรียบเทียบทางเลือกที่เปิดเส้นทางก่อนใช้ตัดสินใจ"
    : illustration
      ? "ตรวจสอบความเชื่อมต่อถนน ตัวตนโรงพยาบาล และทางเข้า/การเปิดบริการ พร้อมยืนยันขอบเขตน้ำท่วมที่ตรงกับเหตุการณ์ก่อนเปรียบเทียบการหยุดชะงัก"
      : "ตรวจสอบข้อมูลประชากร โครงข่ายถนน และจุดหมายบริการที่เข้าเกณฑ์ของพื้นที่นี้ พร้อมยืนยันขอบเขตน้ำท่วมที่ตรงกับเหตุการณ์ก่อนประเมินการหยุดชะงัก";
  const sourceTime = scenario?.candidate_flood_source_timestamp ?? projected.source_timestamp;
  const timeEn = sourceTime ? `Candidate scene acquisition: ${sourceTime} (UTC).` : "Source observation time is not available in this projection.";
  const timeTh = sourceTime ? `เวลารับภาพฉากทัศน์: ${sourceTime} (UTC)` : "ฉบับเผยแพร่นี้ยังไม่มีเวลาสังเกตการณ์ที่เข้าเกณฑ์";
  return [
    ["1 · Priority status", "1 · สถานะลำดับความสำคัญ",
      "Accepted FPPS and A-E action class are unavailable. This low-confidence candidate is for verification only.",
      "ยังไม่มีคะแนน FPPS หรือระดับการดำเนินการ A-E ที่ผ่านการยอมรับ กรณีความเชื่อมั่นต่ำนี้ใช้เพื่อจัดลำดับการตรวจสอบเท่านั้น"],
    ["2 · Focus and denominator", "2 · พื้นที่และตัวหาร", denominatorEn, denominatorTh],
    ["3 · Modelled service access", "3 · การเข้าถึงบริการตามแบบจำลอง",
      `${accessEn} Main-road access has no separately qualified service result; road-graph connectivity does not establish real passability.`,
      `${accessTh} การเข้าถึงถนนสายหลักยังไม่มีผลบริการแยกที่ผ่านการตรวจสอบ ความเชื่อมต่อของโครงข่ายไม่ยืนยันสภาพถนนจริง`],
    ["4 · Scenario and next check", "4 · ฉากทัศน์และสิ่งที่ต้องตรวจ", `${scenarioEn} ${taskEn}`, `${scenarioTh} ${taskTh}`],
    ["5 · Uncertainty and source time", "5 · ความไม่แน่นอนและเวลาแหล่งข้อมูล",
      `The study event window is ${event.start} to ${event.end}; it is not an observation interval. ${timeEn} Flood-affected population, age equity, facility capacity and current passability are not qualified.`,
      `ช่วงเหตุการณ์ที่ศึกษา ${event.start} ถึง ${event.end} ไม่ใช่ช่วงเวลาสังเกตการณ์ ${timeTh} ยังไม่ผ่านการรับรองจำนวนผู้ได้รับผลกระทบ ความเท่าเทียมตามวัย ความจุสถานที่ และสภาพถนนปัจจุบัน`],
  ];
}

export function renderCaseHtml(item, source, fontCss = "") {
  const { reference, aoi, event, projected } = item;
  const rows = messageRows(item);
  const scenario = projected.services.some((service) => service.variants.some((variant) => variant.candidate_flood_scenario_id !== null));
  const labels = scenario ? [...SOURCE_LABELS, "Modified Copernicus Sentinel candidate scenario"] : SOURCE_LABELS;
  const query = new URLSearchParams({ aoi: reference.aoi_id, event: reference.event_id, version: source.catalog.package_version });
  const content = rows.map(([enLabel, thLabel, en, th]) => `<section class="point"><div lang="en"><h2>${escapeHtml(enLabel)}</h2><p>${escapeHtml(en)}</p></div><div lang="th"><h2>${escapeHtml(thLabel)}</h2><p>${escapeHtml(th)}</p></div></section>`).join("\n");
  const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${escapeHtml(aoi.name)} - ${escapeHtml(event.name)} | FloodGuard candidate brief</title>
<style>${fontCss}
@page { size: A4 landscape; margin: 12mm 14mm; }
* { box-sizing: border-box; }
html { color: #17324b; background: #e8eff2; font-family: "Noto Thai Brief", Tahoma, sans-serif; }
body { margin: 0; padding: 0; font-size: 9pt; line-height: 1.35; }
main { max-width: 1200px; margin: 18px auto; padding: 26px 32px; background: #fff; box-shadow: 0 4px 22px #1432471f; }
.top { display:flex; justify-content:space-between; align-items:start; gap:20px; border-bottom: 3px solid #13a6a4; padding-bottom:10px; }
.eyebrow { color:#006b76; font-size:8pt; font-weight:700; letter-spacing:.08em; text-transform:uppercase; }
h1 { font-size:18pt; line-height:1.22; margin:4px 0 2px; }
.thai-name { font-size:13pt; font-weight:600; margin:0; }
.meta { font-size:7.5pt; color:#496478; text-align:right; max-width:40%; overflow-wrap:anywhere; }
.status { margin: 10px 0 8px; padding:8px 10px; background:#e7f2f1; border-left:4px solid #007d7d; font-weight:700; }
.status span { display:block; }
.point { display:grid; grid-template-columns: 1fr 1fr; gap:18px; padding:7px 0; border-bottom:1px solid #dbe5e8; break-inside:avoid; }
.point h2 { margin:0 0 3px; font-size:9pt; color:#006674; }
.point p { margin:0; }
.footer { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-top:8px; color:#415c6f; font-size:7pt; }
.footer p { margin:0 0 3px; }
.hash { font-family: Consolas, monospace; font-size:6.3pt; overflow-wrap:anywhere; }
.links { margin-top:5px; font-size:7pt; }
a { color:#005f78; }
@media print { html { background:#fff; } main { max-width:none; margin:0; padding:0; box-shadow:none; } .links { display:none; } }
@media (max-width:700px) { main { margin:0; padding:18px; } .top,.point,.footer { display:block; } .meta { max-width:none; text-align:left; } .point > div+div { margin-top:7px; } }
</style></head>
<body data-dataset-mode="candidate" data-official-warning="false" data-accepted-fpps="unavailable" data-case-id="${escapeHtml(reference.id)}" data-source-projection-sha256="${reference.sha256}" data-source-analysis-generated-at="${escapeHtml(projected.source_analysis_generated_at ?? "unavailable")}" data-package-release-generated-at="${escapeHtml(projected.generated_at)}">
<main><header class="top"><div><div class="eyebrow">FloodGuard · Bilingual case brief / สรุปกรณีศึกษา</div><h1>${escapeHtml(aoi.name)} · ${escapeHtml(event.name)}</h1><p class="thai-name" lang="th">${escapeHtml(aoi.name_th)} · ${escapeHtml(event.name_th)}</p></div><div class="meta">Case ${escapeHtml(reference.id)}<br>Package ${escapeHtml(source.catalog.package_version)}<br>Source analysis generated / สร้างผลวิเคราะห์ต้นทาง: ${escapeHtml(projected.source_analysis_generated_at ?? "Unavailable / ยังไม่มี")}<br>Package release generated / สร้างแพ็กเกจเผยแพร่: ${escapeHtml(projected.generated_at)}</div></header>
<div class="status"><span lang="en">Candidate research scenario · low confidence · non-operational · not an official warning</span><span lang="th">ฉากทัศน์วิจัยที่ยังไม่ผ่านการรับรอง · ความเชื่อมั่นต่ำ · ไม่ใช่ระบบปฏิบัติการ · ไม่ใช่คำเตือนทางการ</span></div>
${content}
<footer class="footer"><div><p><strong>Source and scope / แหล่งข้อมูลและขอบเขต:</strong> ${escapeHtml(labels.join("; "))}.</p><p>Study AOI intersections only. Candidate sites and imposed closures are not surveyed entrances or observed road closures. / เฉพาะส่วนตัดกับพื้นที่ศึกษา จุดบริการและการปิดถนนยังเป็นข้อมูล/สมมติฐานที่ต้องตรวจสอบ</p></div><div><p class="hash">Source package SHA-256: ${reference.source_package_sha256}</p><p class="hash">Public projection SHA-256: ${reference.sha256}</p><p class="hash">Projection catalog SHA-256: ${source.catalogSha256}</p></div></footer>
<nav class="links" aria-label="Same case"><a href="/public/?${query}">Public</a> · <a href="/command/?${query}">Planning</a> · <a href="/studio/?${query}">Studio</a></nav>
</main></body></html>\n`;
  assertPublicEvidenceText(html);
  return html;
}

function fontStyles() {
  const fontRoot = resolve(scriptDirectory, "..", "node_modules", "@fontsource-variable", "noto-sans-thai", "files");
  const thai = safeRead(resolve(fontRoot, "noto-sans-thai-thai-wght-normal.woff2"), "Thai font").toString("base64");
  const latin = safeRead(resolve(fontRoot, "noto-sans-thai-latin-wght-normal.woff2"), "Latin font").toString("base64");
  return `@font-face{font-family:"Noto Thai Brief";src:url(data:font/woff2;base64,${latin}) format("woff2");font-style:normal;font-weight:100 900;unicode-range:U+0000-024F;}\n@font-face{font-family:"Noto Thai Brief";src:url(data:font/woff2;base64,${thai}) format("woff2");font-style:normal;font-weight:100 900;unicode-range:U+0E00-0E7F;}`;
}

function pageCount(bytes) {
  return (bytes.toString("latin1").match(/\/Type\s*\/Page\b/g) ?? []).length;
}

export function auditExistingBriefs(directory) {
  if (!existsSync(directory)) return;
  assert(lstatSync(directory).isDirectory() && !lstatSync(directory).isSymbolicLink(), "Existing briefs output is not a regular directory");
  const previous = JSON.parse(safeRead(resolve(directory, "catalog.json"), "existing briefs catalog").toString("utf8"));
  assert(previous.schema_version === "floodguard.case_briefs.v1" && Array.isArray(previous.briefs), "Existing briefs catalog is not an allowlist");
  const names = new Set(["catalog.json"]);
  for (const brief of previous.briefs) {
    assert(ID.test(brief.id), "Unsafe case ID in existing briefs catalog");
    for (const [format, urlKey, hashKey] of [["html", "html_url", "html_sha256"], ["pdf", "pdf_url", "pdf_sha256"]]) {
      const filename = `${brief.id}.${format}`;
      assert(brief[urlKey] === `/briefs/${filename}` && SHA256.test(brief[hashKey]), "Unsafe asset in existing briefs catalog");
      assert(sha256(safeRead(resolve(directory, filename), `existing ${filename}`)) === brief[hashKey], `Existing brief hash mismatch: ${filename}`);
      names.add(filename);
    }
  }
  for (const name of readdirSync(directory)) {
    assert(names.has(name), `Refusing to replace unlisted brief asset: ${name}`);
    assert(lstatSync(resolve(directory, name)).isFile() && !lstatSync(resolve(directory, name)).isSymbolicLink(),
      `Refusing to replace non-file brief asset: ${name}`);
  }
  assert(readdirSync(directory).length === names.size, "Existing briefs directory is incomplete");
}

export async function buildCaseBriefs({ publicDirectory = defaultPublicDirectory, outputDirectory = resolve(publicDirectory, "briefs"), catalogSha256 }) {
  const publicRoot = resolve(publicDirectory);
  const destination = resolve(outputDirectory);
  assert(destination === resolve(publicRoot, "briefs"), "Briefs must be written to the allowlisted public/briefs directory");
  const source = loadBriefSource(publicRoot, catalogSha256);
  const fontCss = fontStyles();
  const stage = mkdtempSync(resolve(publicRoot, "..", ".briefs-stage-"));
  const expectedNames = new Set(["catalog.json", ...source.cases.flatMap(({ reference }) => [`${reference.id}.html`, `${reference.id}.pdf`])]);
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    const outputs = [];
    for (const item of source.cases) {
      const html = renderCaseHtml(item, source, fontCss);
      const htmlName = `${item.reference.id}.html`;
      const pdfName = `${item.reference.id}.pdf`;
      const htmlBytes = Buffer.from(html, "utf8");
      writeFileSync(resolve(stage, htmlName), htmlBytes);
      await page.setContent(html, { waitUntil: "load" });
      await page.evaluate(() => document.fonts.ready);
      const pdfBytes = await page.pdf({ format: "A4", landscape: true, printBackground: true, preferCSSPageSize: true });
      assert(pageCount(pdfBytes) === 1, `Brief is not one page: ${item.reference.id}`);
      writeFileSync(resolve(stage, pdfName), pdfBytes);
      outputs.push({ id: item.reference.id, aoi_id: item.reference.aoi_id, event_id: item.reference.event_id,
        source_projection_sha256: item.reference.sha256, source_package_sha256: item.reference.source_package_sha256,
        html_url: `/briefs/${htmlName}`, html_sha256: sha256(htmlBytes), pdf_url: `/briefs/${pdfName}`, pdf_sha256: sha256(pdfBytes) });
    }
    const manifest = { schema_version: "floodguard.case_briefs.v1", profile: "competition",
      package_version: source.catalog.package_version, source_projection_catalog_sha256: source.catalogSha256,
      source_evidence_catalog_sha256: source.catalog.source_catalog_sha256, briefs: outputs };
    const manifestBytes = jsonBytes(manifest);
    writeFileSync(resolve(stage, "catalog.json"), manifestBytes);
    assert(readdirSync(stage).every((name) => expectedNames.has(name)) && readdirSync(stage).length === expectedNames.size,
      "Generated brief output differs from allowlist");
    auditExistingBriefs(destination);
    const backup = `${destination}.previous-${process.pid}`;
    assert(!existsSync(backup), "Previous brief backup exists; resolve it before rebuilding");
    let movedOld = false;
    try {
      if (existsSync(destination)) { renameSync(destination, backup); movedOld = true; }
      renameSync(stage, destination);
    } catch (error) {
      if (movedOld && !existsSync(destination)) renameSync(backup, destination);
      throw error;
    }
    if (movedOld) {
      assert(dirname(backup) === publicRoot && basename(backup) === `briefs.previous-${process.pid}`, "Unsafe brief backup path");
      rmSync(backup, { recursive: true });
    }
    return { cases: outputs.length, projection_catalog_sha256: source.catalogSha256,
      evidence_catalog_sha256: source.catalog.source_catalog_sha256, brief_catalog_sha256: sha256(manifestBytes),
      output_directory: destination };
  } finally {
    await browser?.close();
    if (existsSync(stage)) {
      assert(dirname(stage) === resolve(publicRoot, "..") && basename(stage).startsWith(".briefs-stage-"), "Unsafe brief staging path");
      rmSync(stage, { recursive: true });
    }
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  const option = (name) => {
    const index = args.indexOf(name);
    return index >= 0 ? args[index + 1] : undefined;
  };
  if (args.length !== 6 || !option("--public-dir") || !option("--output-dir") || !option("--catalog-sha256")) {
    throw new Error("Usage: node scripts/build-case-briefs.mjs --public-dir <apps/web/public> --output-dir <apps/web/public/briefs> --catalog-sha256 <pinned projection catalog SHA-256>");
  }
  buildCaseBriefs({ publicDirectory: option("--public-dir"), outputDirectory: option("--output-dir"), catalogSha256: option("--catalog-sha256") })
    .then((result) => console.log(JSON.stringify(result)))
    .catch((error) => { console.error(error); process.exitCode = 1; });
}
