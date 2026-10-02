import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { readdirSync, readFileSync } from "node:fs";
import { resolve, sep } from "node:path";
import { CASE_REPLAY_BUDGET_BYTES, caseReplayBytes, manifestDirectory, readCaseReplayAssets, timelineManifestUrl } from "./case-replay-inventory.mjs";

const root = resolve(import.meta.dirname, "../../..");
const publicRoot = resolve(root, "apps/web/public");
const prefix = "/studies/c2s-ms-20260915/r1/";
const digest = (bytes) => createHash("sha256").update(bytes).digest("hex");
function readAsset(href) {
  if (!href.startsWith("/studies/") || href.includes("..")) throw new Error(`Invalid study asset path: ${href}`);
  const path = resolve(publicRoot, href.slice(1));
  if (!path.startsWith(`${publicRoot}${sep}`)) throw new Error("Study asset escapes public root");
  return readFileSync(path);
}
function verify(href, sha256, expectedBytes) {
  const bytes = readAsset(href);
  if (digest(bytes) !== sha256 || (expectedBytes != null && bytes.length !== expectedBytes)) throw new Error(`Study asset checksum/length mismatch: ${href}`);
  return bytes;
}
const manifestBytes = readAsset(`${prefix}manifest.json`);
const pin = readFileSync(resolve(root, "apps/web/src/lib/study-report-release.ts"), "utf8").match(/"([a-f0-9]{64})"/)?.[1];
if (digest(manifestBytes) !== pin) throw new Error("Committed study manifest differs from compiled pin");
const manifest = JSON.parse(manifestBytes);
for (const asset of manifest.assets) verify(asset.href, asset.sha256, asset.bytes);
const index = JSON.parse(readAsset(`${prefix}visual-index.json`));
const pngs = new Set();
function visit(value) {
  if (Array.isArray(value)) return value.forEach(visit);
  if (!value || typeof value !== "object") return;
  if (typeof value.url === "string" && value.url.endsWith(".png")) {
    const bytes = verify(value.url, value.sha256);
    if (bytes.toString("ascii", 1, 4) !== "PNG" || bytes.readUInt32BE(16) > 256 || bytes.readUInt32BE(20) > 256) throw new Error(`Invalid preview dimensions: ${value.url}`);
    pngs.add(value.url);
  }
  Object.values(value).forEach(visit);
}
visit(index);
if (index.chips.length !== 111 || pngs.size !== 2147) throw new Error("Incomplete test-chip or preview inventory");
const historical = JSON.parse(readAsset("/studies/mae-sai-geoai/2026-07-30-r1/manifest.json"));
for (const asset of [historical.report, ...historical.assets]) verify(asset.href, asset.sha256, asset.bytes);
// The replay's revision is chosen only by TIMELINE_MANIFEST_URL; every asset is derived from that manifest.
const timelineUrl = timelineManifestUrl();
const { manifest: timeline, assets: timelineFiles } = readCaseReplayAssets(publicRoot, timelineUrl);
const timelineAssets = timelineFiles.slice(1);
// Precache budget: the manifest plus every file it lists must fit in 6.5 MB (throws when over).
const timelineBytes = caseReplayBytes(timelineFiles, CASE_REPLAY_BUDGET_BYTES);
// One revision ships: the study folder holds the served revision only, and that folder holds nothing the manifest
// does not list (an unlisted file would ship without a hash and outside the budget).
const timelineDirectory = resolve(publicRoot, manifestDirectory(timelineUrl).slice(1));
const timelineRevision = timelineDirectory.split(sep).at(-1);
const timelineRevisions = readdirSync(resolve(timelineDirectory, ".."));
if (timelineRevisions.length !== 1 || timelineRevisions[0] !== timelineRevision) {
  throw new Error(`Exactly one Mae Sai timeline revision may ship (${timelineRevision}); found: ${timelineRevisions.join(", ")}`);
}
const timelineListed = new Set(timelineFiles.map((file) => file.url.slice(file.url.lastIndexOf("/") + 1)));
for (const entry of readdirSync(timelineDirectory, { withFileTypes: true })) {
  if (!entry.isFile() || !timelineListed.has(entry.name)) throw new Error(`Mae Sai timeline file is not listed in its manifest: ${entry.name}`);
}
// Every file the page loads must be among the hash-verified ones: the HAND raster, imagery layers, vectors, the
// residents raster and the evacuation-access node file (r2 on), and the VIIRS daily flood maps (r3 on). The evidence envelope (r4 on) is checked below.
const expectedTimelineAssets = [timeline.hand, ...timeline.layers, ...Object.values(timeline.vectors)];
if (timeline.population) expectedTimelineAssets.push(timeline.population);
if (timeline.access) expectedTimelineAssets.push(timeline.access.nodes);
if (timeline.viirs_daily) expectedTimelineAssets.push(...timeline.viirs_daily.days);
for (const asset of expectedTimelineAssets) {
  if (!asset?.href || !timelineAssets.some((file) => file.url === asset.href)) throw new Error(`Timeline asset is not hash-verified: ${asset?.href}`);
}
// VIIRS maps are pre-coloured RGBA PNGs of the declared size; each is an observation with its cloud and clear-sky figures.
for (const day of timeline.viirs_daily?.days ?? []) {
  const bytes = readAsset(day.href);
  if (bytes.toString("ascii", 1, 4) !== "PNG" || bytes.readUInt32BE(16) !== day.width || bytes.readUInt32BE(20) !== day.height || bytes[25] !== 6) {
    throw new Error(`VIIRS map is not an RGBA PNG of its declared size: ${day.href}`);
  }
  if (!(day.cloud_share >= 0 && day.cloud_share <= 1) || !(day.clear_km2 >= 0) || !Number.isFinite(day.t) || !day.nominal_local_time) {
    throw new Error(`VIIRS day lacks its cloud share, clear area or nominal time: ${day.date}`);
  }
}
// Hourly rain: one value (or null) per replay hour for every gauge, matching the baked totals.
if (timeline.rainfall) {
  const hours = timeline.days.length * 24;
  for (const station of timeline.rainfall.stations) {
    const series = timeline.rainfall.hourly_mm[station.code];
    if (!Array.isArray(series) || series.length !== hours) throw new Error(`Rain gauge ${station.code} does not cover the ${hours} replay hours`);
    const values = series.filter((value) => typeof value === "number");
    const total = values.reduce((sum, value) => sum + value, 0);
    if (Math.abs(total - station.total_mm) > 0.05 || Math.max(0, ...values) !== station.max_hour_mm || series.length - values.length !== station.missing_hours) {
      throw new Error(`Rain gauge ${station.code} totals differ from its hourly record`);
    }
  }
  if (!timeline.rainfall.licence || !timeline.rainfall.source_url) throw new Error("Mae Sai rainfall must carry its licence and source");
}
if (timeline.access) {
  const { nodes, sets } = timeline.access;
  const cut = nodes.layout.find((field) => field.name === "cut_codes");
  if (!cut || cut.shape?.[0] !== sets.length || cut.shape?.[1] !== nodes.count || cut.offset + sets.length * nodes.count !== nodes.bytes) {
    throw new Error("Mae Sai access node layout does not match its declared sets, count and size");
  }
}
if (timeline.population && (timeline.population.width !== timeline.hand.width || timeline.population.height !== timeline.hand.height)) {
  throw new Error("Mae Sai residents raster must share the HAND grid");
}
if (timeline.real_time !== false || timeline.official_warning !== false || !timeline.confidence || !timeline.source_timestamp) {
  throw new Error("Mae Sai timeline must declare confidence, source timestamp and non-real-time, non-warning status");
}
// Evidence envelope: no score, no action class, non-operational, a generation time, input hashes, and a lane and a
// source timestamp for every evidence block. The full contract is the JSON schema, checked by pytest.
if (timeline.accepted_fpps !== null || timeline.accepted_action_class !== null || timeline.operational_status !== "non_operational"
  || timeline.can_feed_decision_layer !== false || timeline.revision !== timelineRevision) {
  throw new Error("Mae Sai timeline must be non-operational, with null accepted score and class, and name its own revision");
}
if (Number.isNaN(Date.parse(timeline.generated_at)) || !Array.isArray(timeline.input_sha256) || timeline.input_sha256.length === 0
  || !timeline.input_sha256.every((input) => /^[a-f0-9]{64}$/.test(input.sha256) && typeof input.path === "string")) {
  throw new Error("Mae Sai timeline must carry generated_at and the SHA-256 of every input");
}
if (!Array.isArray(timeline.evidence_blocks) || timeline.evidence_blocks.length === 0
  || !timeline.evidence_blocks.every((block) => block.lane && block.source_timestamp && block.evidence_tier && block.temporal_relation)) {
  throw new Error("Every Mae Sai evidence block must carry its lane, tier, temporal relation and source timestamp");
}

// Windows newline conversion must not change a hash-bound artifact on checkout.
const entries = execFileSync("git", ["ls-files", "--stage", "-z", "apps/web/public/studies"], { cwd: root, encoding: "utf8" }).split("\0").filter(Boolean);
for (const entry of entries) {
  const [info, path] = entry.split("\t");
  const [, blobId] = info.split(" ");
  const bytes = readFileSync(resolve(root, path));
  const actual = createHash("sha1").update(`blob ${bytes.length}\0`).update(bytes).digest("hex");
  if (actual !== blobId) throw new Error(`Git changes exact study bytes or has stale staged content: ${path}`);
}
console.log(`Study integrity passed: ${manifest.assets.length} C2S JSON assets, ${pngs.size} previews, ${historical.assets.length + 1} historical assets, ${timelineAssets.length} Mae Sai timeline assets (${timeline.revision}, ${timelineBytes} of ${CASE_REPLAY_BUDGET_BYTES} budget bytes) and ${entries.length} byte-identical Git blobs.`);
