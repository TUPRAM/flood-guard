import type {
  BenchmarkSummary, MaeSaiReport, RtcReport, StudyAsset, StudyManifest,
  StudyMetrics, StudyModelDetail, StudyScore, StudySummary, StudyGeography, JsonObject,
} from "./study-report-types";
import { STUDY_MANIFEST_SHA256 } from "./study-report-release";

export * from "./study-report-types";
export const STUDY_BASE = "/studies/c2s-ms-20260915/r1/";
const SHA = /^[a-f0-9]{64}$/;
const ROLES = ["train", "tune", "calibration", "selection", "test"];
const MODELS = ["random_forest", "xgboost", "unet", "vh_otsu"];
const PRIVATE_PATH = /(?:^|[^A-Za-z0-9_])[A-Za-z]:[\\/]|\\\\|file:\/\/|\/(?:Users|home|root)\//;
type RecordValue = Record<string, unknown>;
type Fetcher = typeof fetch;

function fail(message: string): never { throw new Error(`Study evidence unavailable: ${message}`); }
function record(value: unknown, label: string): RecordValue {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail(`${label} must be an object.`);
  return value as RecordValue;
}
function list(value: unknown, label: string): unknown[] {
  if (!Array.isArray(value)) fail(`${label} must be an array.`);
  return value;
}
function text(value: unknown, label: string): string {
  if (typeof value !== "string" || !value.trim()) fail(`${label} is missing.`);
  return value;
}
function integer(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) fail(`${label} must be a nonnegative integer.`);
  return value;
}
function number(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) fail(`${label} must be finite.`);
  return value;
}
function unit(value: unknown, label: string): number {
  const n = number(value, label);
  if (n < 0 || n > 1) fail(`${label} is outside [0,1].`);
  return n;
}
function strings(value: unknown, label: string): string[] {
  return list(value, label).map((item) => text(item, label));
}
function oneOf(value: unknown, choices: string[], label: string): string {
  const name = text(value, label);
  if (!choices.includes(name)) fail(`Unknown ${label}.`);
  return name;
}
function sha(value: unknown): string {
  const hash = text(value, "digest");
  if (!SHA.test(hash)) fail("Malformed SHA-256.");
  return hash;
}
function unique(values: string[], label: string): void {
  if (new Set(values).size !== values.length) fail(`Duplicate ${label}.`);
}
function safeJson(value: unknown): void {
  if (typeof value === "string") {
    if (PRIVATE_PATH.test(value) || value.startsWith("//")) fail("Private paths are not public study evidence.");
    for (const url of value.match(/https?:\/\/[^\s"<>]+/g) ?? []) {
      const parsed = new URL(url);
      if (parsed.username || parsed.password || [...parsed.searchParams.keys()].some(
        (key) => ["sig", "token", "access_token", "api_key", "password"].includes(key.toLowerCase()),
      )) fail("Authenticated URLs are not public study evidence.");
    }
  } else if (typeof value === "number") number(value, "JSON number");
  else if (Array.isArray(value)) value.forEach(safeJson);
  else if (value && typeof value === "object") Object.values(value).forEach(safeJson);
}

function base(value: unknown, kind: string): RecordValue {
  safeJson(value);
  const data = record(value, kind);
  if (data.schema_version !== `floodguard.study-${kind}.v1`
    || data.study_id !== "c2s-ms-20260915" || data.revision !== "r1") fail("Study identity or schema mismatch.");
  if (data.aggregation_status !== "report_only" || data.operational_status !== "non_operational"
    || data.can_feed_decision_layer !== false || data.official_warning !== false) fail("Study safety scope mismatch.");
  text(data.confidence, "confidence");
  text(data.source_timestamp, "source timestamp");
  text(data.data_mode, "data mode");
  record(data.license, "license");
  strings(data.assumptions, "assumptions");
  return data;
}

export function validateStudyAsset(value: unknown): StudyAsset {
  const asset = record(value, "asset");
  const href = text(asset.href, "asset href");
  if (!href.startsWith(STUDY_BASE) || !/^[A-Za-z0-9/_.-]+\.json$/.test(href)
    || href.includes("..") || href.includes("//")) fail("Asset escapes the immutable study revision.");
  sha(asset.sha256);
  const bytes = integer(asset.bytes, "asset length");
  if (!bytes || bytes > 32 * 1024 * 1024) fail("Asset size is outside the JSON budget.");
  text(asset.label, "asset label");
  text(asset.transformation, "asset transformation");
  if (asset.media_type !== "application/json") fail("Unexpected study media type.");
  if (asset.source_sha256 !== null) sha(asset.source_sha256);
  return asset as unknown as StudyAsset;
}

function checkReceipt(value: unknown): void {
  const r = record(value, "source receipt");
  const path = text(r.source_path, "source path");
  if (path.startsWith("/") || path.includes("..") || path.includes(":")) fail("Source receipt path is not relative.");
  sha(r.sha256); integer(r.bytes, "source bytes");
}

function checkMetrics(value: unknown): StudyMetrics {
  const m = record(value, "metrics");
  for (const key of ["iou", "f1_dice", "precision", "recall", "brier", "ece", "error_rate"]) {
    if (m[key] !== null) unit(m[key], key);
  }
  const pixels = integer(m.n_pixels, "metric pixels");
  const positive = integer(m.n_reference_positive, "reference positives");
  const tp = integer(m.true_positive, "true positive");
  const fp = integer(m.false_positive, "false positive");
  const tn = integer(m.true_negative, "true negative");
  const fn = integer(m.false_negative, "false negative");
  if (tp + fp + tn + fn !== pixels || tp + fn !== positive) fail("Confusion matrix and support differ.");
  const bins = list(m.reliability, "reliability bins");
  let binned = 0;
  for (const value of bins) {
    const b = record(value, "reliability bin");
    if (unit(b.bin_lo, "bin low") >= unit(b.bin_hi, "bin high")) fail("Invalid reliability bin.");
    binned += integer(b.n, "bin support");
    for (const key of ["mean_predicted", "observed_frequency"]) if (b[key] !== null) unit(b[key], key);
  }
  if (binned !== pixels) fail("Reliability bin support differs from metrics.");
  return m as unknown as StudyMetrics;
}

function checkScore(value: unknown): StudyScore {
  const s = record(value, "score");
  const full = checkMetrics(s.full_valid);
  const selective = checkMetrics(s.selective);
  const n = integer(s.n_valid_pixels, "valid pixels");
  const coverage = unit(s.coverage, "coverage");
  if (n !== full.n_pixels || selective.n_pixels > n
    || (n > 0 && Math.abs(coverage - selective.n_pixels / n) > 1e-10)) fail("Selective coverage does not match support.");
  return s as unknown as StudyScore;
}

function scorePair(value: unknown, calibrationRequired = true): void {
  const pair = record(value, "score pair");
  const raw = checkScore(pair.raw);
  if (calibrationRequired || pair.calibrated !== undefined) {
    const calibrated = checkScore(pair.calibrated);
    if (raw.n_valid_pixels !== calibrated.n_valid_pixels) fail("Raw and calibrated support differ.");
  }
}

function checkBenchmark(value: unknown, withDetail = true): BenchmarkSummary {
  const b = record(value, "benchmark");
  const arm = oneOf(b.arm, ["sar", "context"], "arm");
  const model = oneOf(b.model, MODELS, "model");
  if (b.id !== `${arm}/${model}`) fail("Benchmark identity mismatch.");
  for (const field of ["dataset", "source_timestamp", "processed_utc"]) text(b[field], field);
  const inventory = integer(b.inventory_chips, "inventory chips");
  if (integer(b.supported_chips, "supported chips") + integer(b.invalid_chips, "invalid chips") !== inventory) fail("Chip support does not reconcile.");
  scorePair(b);
  const events = record(b.per_event, "event metrics");
  Object.values(events).forEach((item) => scorePair(item));
  if (Object.keys(events).length !== integer(b.n_test_events, "test events")) fail("Test event count differs.");
  for (const mode of ["raw", "calibrated"]) {
    const total = Object.values(events).reduce<number>((sum, item) => sum + checkScore(record(item, "event")[mode]).n_valid_pixels, 0);
    if (total !== checkScore(b[mode]).n_valid_pixels) fail("Pooled and event support differ.");
  }
  const macro = record(b.event_macro_iou, "macro IoU");
  unit(macro.raw, "macro raw"); unit(macro.calibrated, "macro calibrated");
  if (macro.n_events !== b.n_test_events || macro.confidence_interval !== "not_estimated") fail("Macro evidence scope mismatch.");
  if (b.combined_screening !== null) {
    const c = record(b.combined_screening, "combined screening");
    const n = integer(c.n_original_valid_pixels, "original support");
    const accepted = integer(c.n_accepted_pixels, "accepted support");
    const vetoed = integer(c.n_context_vetoed, "vetoed pixels");
    if (n !== checkScore(b.raw).n_valid_pixels || accepted > n || vetoed > n
      || checkMetrics(c.metrics_on_accepted_pixels).n_pixels !== accepted
      || Math.abs(unit(c.coverage_of_original_valid_pixels, "combined coverage") - accepted / n) > 1e-10) fail("Combined screening support mismatch.");
  }
  if (b.calibration !== null && record(b.calibration, "calibration").fitted_on_role !== "calibration") fail("Calibration fitted on the wrong role.");
  if (b.abstention !== null && record(b.abstention, "abstention").fitted_on_role !== "selection") fail("Abstention fitted on the wrong role.");
  checkReceipt(b.source);
  const download = validateStudyAsset(b.download);
  if (download.source_sha256 !== record(b.source, "benchmark receipt").sha256) fail("Public download and original benchmark are not bound.");
  if (withDetail) validateStudyAsset(b.detail);
  return b as unknown as BenchmarkSummary;
}

export function validateStudySummary(value: unknown): StudySummary {
  const s = base(value, "summary");
  const counts = record(s.counts, "counts");
  if (counts.chips !== 900 || counts.events !== 18 || counts.files !== 2700
    || counts.scenes !== 36 || counts.download_bytes !== 1514731043) fail("Full dataset identity differs.");
  text(s.title, "title"); text(s.dataset, "dataset");
  text(s.processed_utc, "processing time"); text(s.partition_frozen_utc, "partition time");
  const events = list(s.events, "events").map((item) => record(item, "event"));
  unique(events.map((e) => text(e.event_id, "event ID")), "event ID");
  if (events.length !== 18 || events.reduce((n, e) => n + integer(e.n_chips, "event chips"), 0) !== 900) fail("Event counts differ.");
  for (const e of events) {
    oneOf(e.role, ROLES, "role");
    if (e.country !== null) text(e.country, "country");
    text(e.country_source, "country source");
    const bbox = list(e.bbox, "bbox").map((v) => number(v, "coordinate"));
    const center = list(e.centroid_lon_lat, "center").map((v) => number(v, "coordinate"));
    if (bbox.length !== 4 || center.length !== 2 || bbox[0] >= bbox[2] || bbox[1] >= bbox[3]
      || bbox[0] < -180 || bbox[2] > 180 || bbox[1] < -90 || bbox[3] > 90
      || Math.abs(center[0] - (bbox[0] + bbox[2]) / 2) > 1e-8
      || Math.abs(center[1] - (bbox[1] + bbox[3]) / 2) > 1e-8) fail("Invalid event geography.");
    strings(e.scene_ids, "scenes"); strings(e.source_timestamps, "source dates");
    text(e.source_start, "source start"); text(e.source_end, "source end");
  }
  const roles = list(s.roles, "roles").map((item) => record(item, "role"));
  unique(roles.map((r) => oneOf(r.role, ROLES, "role")), "role");
  if (roles.length !== 5) fail("Five distinct partition roles are required.");
  for (const r of roles) {
    const members = events.filter((e) => e.role === r.role);
    const ids = strings(r.event_ids, "role events").sort();
    if (r.n_events !== members.length || r.n_chips !== members.reduce((sum, e) => sum + Number(e.n_chips), 0)
      || JSON.stringify(ids) !== JSON.stringify(members.map((e) => e.event_id).sort())) fail("Role membership differs.");
    text(r.purpose, "role purpose");
  }
  record(s.partition, "partition");
  list(s.provenance, "provenance").forEach(checkReceipt);
  const benchmarks = list(s.benchmarks, "benchmarks").map((item) => checkBenchmark(item));
  unique(benchmarks.map((b) => b.id), "benchmark");
  const expectedIds = ["context/random_forest", "context/unet", "context/xgboost", "sar/random_forest", "sar/unet", "sar/vh_otsu", "sar/xgboost"];
  if (benchmarks.map((b) => b.id).sort().join() !== expectedIds.join()) fail("Frozen benchmark models differ.");
  if (benchmarks.length !== 7 || benchmarks.some((b) => b.inventory_chips !== 111 || b.n_test_events !== 3
    || Object.keys(b.per_event).some((id) => !events.some((e) => e.event_id === id && e.role === "test")))) fail("Benchmark test scope differs.");
  if (benchmarks.some((b) => b.invalid_chips !== (b.arm === "context" ? 11 : 0)
    || b.raw.n_valid_pixels !== (b.arm === "context" ? 24452094 : 27693531))) fail("Frozen support mask differs.");
  validateStudyAsset(s.rtc); validateStudyAsset(s.mae_sai);
  if (s.geography !== null) validateStudyAsset(s.geography);
  if (s.visuals !== null) validateStudyAsset(s.visuals);
  list(s.downloads, "downloads").forEach(validateStudyAsset);
  strings(s.limitations, "limitations");
  list(s.findings, "findings").forEach((item) => record(item, "finding"));
  for (const value of list(s.sources, "sources")) {
    const source = record(value, "source");
    for (const field of ["id", "name", "version", "purpose", "source_period", "license", "attribution"]) text(source[field], field);
    strings(source.limitations, "source limitations");
    for (const item of list(source.links, "source links")) {
      const link = record(item, "source link"); text(link.label, "link label");
      if (new URL(text(link.href, "source URL")).protocol !== "https:") fail("Source link is not HTTPS.");
    }
  }
  return s as unknown as StudySummary;
}

export function validateStudyModelDetail(value: unknown): StudyModelDetail {
  const d = base(value, "model");
  checkBenchmark(d.benchmark, false);
  if (d.training !== null) {
    const t = record(d.training, "training"); strings(t.feature_names, "features"); record(t.feature_units, "units");
    record(t.fit, "fit");
    if (t.checkpoint !== null) checkReceipt(t.checkpoint);
    if (t.feature_manifest !== null) checkReceipt(t.feature_manifest);
    if (t.download !== null) validateStudyAsset(t.download);
  }
  const chips = list(d.per_chip, "per-chip evidence").map((item) => record(item, "chip"));
  if (chips.length !== record(d.benchmark, "benchmark").inventory_chips) fail("Per-chip inventory differs.");
  for (const item of list(d.risk_coverage_curve, "risk curve")) {
    const r = record(item, "risk point"); unit(r.confidence_cutoff, "cutoff"); unit(r.coverage, "coverage");
    if (r.error_rate !== null) unit(r.error_rate, "risk");
  }
  if (d.tree_shap !== null) {
    const t = record(d.tree_shap, "TreeSHAP"); text(t.method, "method"); integer(t.n_samples, "SHAP samples");
    text(t.role, "SHAP role"); record(t.feature_units, "SHAP units"); strings(t.assumptions, "SHAP assumptions");
    const names = strings(t.feature_names, "SHAP names");
    const values = list(t.mean_absolute_contribution, "SHAP values");
    if (values.length !== names.length || values.some((v) => number(v, "SHAP contribution") < 0)) fail("Invalid SHAP dimensions.");
  }
  return d as unknown as StudyModelDetail;
}

export function validateStudyRtc(value: unknown): RtcReport {
  const d = base(value, "rtc");
  const arms = list(d.arms, "RTC arms").map((item) => record(item, "RTC arm"));
  unique(arms.map((a) => oneOf(a.arm, ["sar", "context"], "RTC arm")), "RTC arm");
  if (arms.length !== 2) fail("Both RTC arms are required.");
  for (const a of arms) {
    if (a.n_paired_test_chips !== 46 || a.n_excluded_chips !== 65 || a.n_full_test_chips !== 111 || a.n_paired_events !== 2) fail("RTC matched subset differs.");
    const pooled = record(a.pooled, "RTC pooled");
    if (Object.keys(pooled).sort().join() !== "fixed_ramp,random_forest,unet,xgboost") fail("RTC methods differ.");
    for (const pair of Object.values(pooled)) {
      scorePair(pair, false);
      if (checkScore(record(pair, "RTC pair").raw).n_valid_pixels !== a.common_valid_pixels) fail("RTC common support differs.");
    }
    const events = record(a.per_event, "RTC event results");
    if (Object.keys(events).length !== 2) fail("RTC event count differs.");
    Object.values(events).forEach((item) => Object.values(record(item, "RTC event")).forEach((pair) => scorePair(pair, false)));
    strings(a.assumptions, "RTC assumptions"); text(a.source_timestamp, "RTC source time");
    checkReceipt(a.source); validateStudyAsset(a.download);
  }
  record(d.acquisition, "RTC acquisition");
  return d as unknown as RtcReport;
}

export function validateStudyMaeSai(value: unknown): MaeSaiReport {
  const d = base(value, "mae-sai");
  if (d.accuracy_status !== "unavailable_no_qualified_Thai_reference" || d.metrics !== null) fail("Mae Sai has no independent accuracy evidence.");
  const records = list(d.records, "inference records").map((item) => record(item, "inference record"));
  unique(records.map((r) => text(r.id, "record ID")), "inference record");
  if (records.length !== 6) fail("Six frozen inference records are required.");
  for (const r of records) {
    const arm = oneOf(r.arm, ["sar", "context"], "inference arm");
    const model = oneOf(r.model, MODELS.slice(0, 3), "inference model");
    if (r.id !== `${arm}/${model}` || r.accuracy_status !== d.accuracy_status || r.metrics !== null) fail("Inference identity or scope mismatch.");
    const valid = integer(r.valid_pixels, "inference valid pixels");
    const accepted = integer(r.accepted_pixels, "inference accepted pixels");
    if (valid !== 2618380 || accepted > valid || Math.abs(unit(r.accepted_fraction, "acceptance") - accepted / valid) > 1e-10) fail("Inference support differs.");
    checkReceipt(r.layers); checkReceipt(r.source); sha(r.benchmark_sha256); sha(r.checkpoint_sha256);
    text(r.source_timestamp, "inference source time"); text(r.processed_utc, "inference processing time");
    for (const key of ["grid", "calibration", "abstention_policy", "context_screening"]) record(r[key], key);
    validateStudyAsset(r.download);
  }
  strings(d.bands, "inference bands"); record(d.source_pair, "source pair");
  return d as unknown as MaeSaiReport;
}

function validateManifest(value: unknown): StudyManifest {
  const d = base(value, "manifest");
  const summary = validateStudyAsset(d.summary);
  const assets = list(d.assets, "manifest assets").map(validateStudyAsset);
  unique(assets.map((a) => a.href), "manifest asset");
  if (!assets.some((a) => a.href === summary.href && a.sha256 === summary.sha256 && a.bytes === summary.bytes)) fail("Summary is not bound to the manifest.");
  return d as unknown as StudyManifest;
}

async function fetchBytes(href: string, expectedHash: string, expectedBytes: number | null, fetcher: Fetcher): Promise<unknown> {
  const response = await fetcher(href, { cache: "no-store", credentials: "same-origin", redirect: "error" });
  if (!response.ok) fail(`HTTP ${response.status} for the requested study asset.`);
  const bytes = await response.arrayBuffer();
  if (bytes.byteLength > 32 * 1024 * 1024 || (expectedBytes !== null && bytes.byteLength !== expectedBytes)) fail("Downloaded byte count mismatch.");
  const actual = [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))].map((b) => b.toString(16).padStart(2, "0")).join("");
  if (actual !== expectedHash) fail("Downloaded SHA-256 mismatch.");
  return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes)) as unknown;
}

async function loadManifest(fetcher: Fetcher): Promise<StudyManifest> {
  return validateManifest(await fetchBytes(STUDY_BASE + "manifest.json", STUDY_MANIFEST_SHA256, null, fetcher));
}

async function loadBoundAsset(asset: StudyAsset, fetcher: Fetcher): Promise<unknown> {
  validateStudyAsset(asset);
  const manifest = await loadManifest(fetcher);
  if (!manifest.assets.some((item) => item.href === asset.href && item.sha256 === asset.sha256 && item.bytes === asset.bytes)) fail("Requested asset is not in the pinned release.");
  return fetchBytes(asset.href, asset.sha256, asset.bytes, fetcher);
}

export async function loadStudySummary(fetcher: Fetcher = fetch): Promise<StudySummary> {
  const manifest = await loadManifest(fetcher);
  return validateStudySummary(await fetchBytes(manifest.summary.href, manifest.summary.sha256, manifest.summary.bytes, fetcher));
}
export async function loadStudyModelDetail(asset: StudyAsset, fetcher: Fetcher = fetch): Promise<StudyModelDetail> {
  const detail = validateStudyModelDetail(await loadBoundAsset(asset, fetcher));
  if (asset.href !== `${STUDY_BASE}models/${detail.benchmark.id.replace("/", "-")}.json`) fail("Requested model and returned detail differ.");
  return detail;
}
export async function loadStudyRtc(asset: StudyAsset, fetcher: Fetcher = fetch): Promise<RtcReport> {
  return validateStudyRtc(await loadBoundAsset(asset, fetcher));
}
export async function loadStudyMaeSai(asset: StudyAsset, fetcher: Fetcher = fetch): Promise<MaeSaiReport> {
  return validateStudyMaeSai(await loadBoundAsset(asset, fetcher));
}

/** Read an allowlisted, digest-bound display index without operational fallback. */
export async function loadStudyJsonAsset(asset: StudyAsset, fetcher: Fetcher = fetch): Promise<JsonObject> {
  const value = await loadBoundAsset(asset, fetcher);
  safeJson(value);
  const data = record(value, "display artifact");
  const safety = asset.href === `${STUDY_BASE}visual-index.json` && data.schema_version === 1
    ? record(data.metadata, "visual safety metadata") : data;
  if (data.study_id !== "c2s-ms-20260915" || data.revision !== "r1"
    || safety.can_feed_decision_layer !== false || safety.official_warning !== false
    || safety.aggregation_status !== "report_only") fail("Display artifact scope mismatch.");
  return data as JsonObject;
}

export async function loadStudyGeography(asset: StudyAsset, fetcher: Fetcher = fetch): Promise<StudyGeography> {
  const data = await loadStudyJsonAsset(asset, fetcher);
  if (data.schema_version !== "floodguard.study-geography.v1") fail("Geography schema mismatch.");
  sha(data.source_sha256); integer(data.source_bytes, "geography source bytes");
  text(data.license, "geography license");
  if (new URL(text(data.license_url, "license URL")).protocol !== "https:") fail("Geography license URL is not HTTPS.");
  const countries = record(data.event_countries, "geographic country inference");
  Object.values(countries).forEach((name) => text(name, "country"));
  for (const value of list(data.features, "geographic features")) {
    const feature = record(value, "geographic feature");
    text(feature.name, "feature name");
    if (!/^[MmLlZz0-9.,\s+-]+$/.test(text(feature.path, "outline path"))) fail("Invalid geographic SVG path.");
  }
  return data as unknown as StudyGeography;
}
