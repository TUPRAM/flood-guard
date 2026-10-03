import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { readdirSync, readFileSync } from "node:fs";
import { resolve, sep } from "node:path";
import {
  CASE_REPLAY_BUDGET_BYTES, CASE_REPLAY_ENVELOPE_FOLDER, CASE_REPLAY_EXPORT_BUDGET_BYTES, CASE_REPLAY_EXPORT_KEY, caseReplayBytes, caseReplayExportBytes,
  manifestDirectory, readCaseReplayAssets, readCaseReplayExports, timelineManifestUrl,
} from "./case-replay-inventory.mjs";

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
const timelineBase = manifestDirectory(timelineUrl);
const timelineListed = new Set(timelineFiles.map((file) => file.url.slice(timelineBase.length)));
for (const entry of readdirSync(timelineDirectory, { withFileTypes: true })) {
  // Two folders are allowed beside the files: the export pack, checked below against its own list and budget, and the
  // season envelope's folder, whose files are listed in the manifest like any other asset (checked below too).
  if (entry.isDirectory() && entry.name === CASE_REPLAY_EXPORT_KEY && timeline.exports) continue;
  if (entry.isDirectory() && entry.name === CASE_REPLAY_ENVELOPE_FOLDER && timeline.season_envelope) {
    for (const file of readdirSync(resolve(timelineDirectory, entry.name), { withFileTypes: true })) {
      if (!file.isFile() || !timelineListed.has(`${entry.name}/${file.name}`)) throw new Error(`Mae Sai season-envelope file is not listed in its manifest: ${file.name}`);
    }
    continue;
  }
  if (!entry.isFile() || !timelineListed.has(entry.name)) throw new Error(`Mae Sai timeline file is not listed in its manifest: ${entry.name}`);
}
// Export pack: download files, hash-verified against the manifest, outside the precache set and under their own
// budget (throws when over). The folder holds nothing the manifest does not list, and no file of it is precached.
const exportFiles = timeline.exports ? readCaseReplayExports(publicRoot, timelineUrl) : [];
const exportBytes = caseReplayExportBytes(exportFiles, CASE_REPLAY_EXPORT_BUDGET_BYTES);
if (timeline.exports) {
  const exportDirectory = resolve(timelineDirectory, CASE_REPLAY_EXPORT_KEY);
  const exportListed = new Set(exportFiles.map((file) => file.url.slice(file.url.lastIndexOf("/") + 1)));
  for (const entry of readdirSync(exportDirectory, { withFileTypes: true })) {
    if (!entry.isFile() || !exportListed.has(entry.name)) throw new Error(`Mae Sai export file is not listed in its manifest: ${entry.name}`);
  }
  if (exportFiles.length !== timeline.exports.file_count || exportBytes !== timeline.exports.bytes) {
    throw new Error("Mae Sai export pack differs from the file count and size its manifest states");
  }
  if (timelineFiles.some((file) => file.url.includes(`/${CASE_REPLAY_EXPORT_KEY}/`))) throw new Error("An export file is in the replay's precache set");
  for (const file of timeline.exports.files) {
    // A modelled table is never named as a timetable of closures, and nothing here may come from product 4009.
    if (/schedule|closure|cut[-_]?off|unosat|4009/i.test(file.name) || file.licence !== "ODbL 1.0" || !file.source_ids.includes("osm")
      || file.source_ids.some((id) => ["hii-rain", "viirs", "unosat-4009"].includes(id))) {
      throw new Error(`Mae Sai export file breaks its naming or licence rule: ${file.name}`);
    }
    const bytes = readAsset(file.href);
    if (bytes.includes(13)) throw new Error(`Mae Sai export file has CR line ends: ${file.name}`);
    const isCsv = file.media_type === "text/csv";
    // A CSV starts with a UTF-8 byte-order mark (Thai text opens correctly in Excel) and its provenance lines.
    if (isCsv !== (bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf)) throw new Error(`Mae Sai export file has the wrong byte-order mark: ${file.name}`);
    const text = bytes.toString("utf8");
    for (const needle of ["T1 scenario (model) replay of a reconstructed 2024 event", "not a forecast, not an observed closure record, not an official warning",
      "non_operational", timeline.generated_at, "confidence_class", "source_timestamp", "assumption_1", "input_set_sha256="]) {
      if (!text.includes(needle)) throw new Error(`Mae Sai export file lacks "${needle}" in its header: ${file.name}`);
    }
  }
  if (!/^T1 scenario \(model\) replay/.test(timeline.exports.tier) || timeline.exports.confidence !== "low") {
    throw new Error("Mae Sai export pack lacks its tier sentence");
  }
  if (timeline.shelters?.verification?.status === "not_conducted" && timeline.shelters.verification.checked.length !== 0) {
    throw new Error("A shelter check that was not conducted states results");
  }
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
// Season envelope (UNOSAT and GISTDA product 4009, a scenario layer): three files in a folder of their own, under CC BY-SA 4.0
// with the credit and a change notice. The manifest names them by address, hash and size and holds no figure of theirs;
// nothing of the envelope is a day observation, a replay layer or an export file. Without its label, its standard sentence
// (preliminary, not validated by FloodGuard) or a credit that names its holders it must not ship. The statistics file also
// holds figures from other open data: it and the licence notice must name each with its own licence and credit.
const envelopeFolder = `${timelineBase}${CASE_REPLAY_ENVELOPE_FOLDER}/`;
const envelopeUrls = timelineFiles.filter((file) => file.url.startsWith(envelopeFolder)).map((file) => file.url.slice(envelopeFolder.length)).sort();
if (!timeline.season_envelope) {
  if (envelopeUrls.length > 0) throw new Error("Season-envelope files are listed without a season_envelope block");
} else {
  const envelope = timeline.season_envelope;
  const credit = "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009";
  if (envelopeUrls.join(",") !== "LICENSE,envelope.json,envelope.png") throw new Error(`The season envelope must ship exactly its raster, statistics and licence files: ${envelopeUrls.join(", ")}`);
  for (const key of ["raster", "statistics", "licence"]) {
    const file = envelope.files?.[key];
    if (!file || Object.keys(file).sort().join(",") !== "bytes,href,sha256" || !file.href.startsWith(envelopeFolder)) {
      throw new Error(`season_envelope.files.${key} must give href, sha256 and bytes only, inside the envelope's folder`);
    }
  }
  // The holders the credit begins with: a short credit that names the licence and nobody credits nobody.
  const holders = credit.split(",", 1)[0].trim();
  if (envelope.lane !== "SCN-ENV" || envelope.shown !== true || envelope.day_independent !== true || envelope.licence !== "CC BY-SA 4.0"
    || envelope.credit !== credit || !String(envelope.map_credit).includes("CC BY-SA 4.0") || !String(envelope.label).startsWith("Scenario (SCN-ENV)")
    || !String(envelope.caption).includes("not an observation for any replay day")) {
    throw new Error("The season envelope lacks its scenario lane, label, caption, licence or credit, so it must not ship");
  }
  if (!holders || !String(envelope.map_credit).includes(holders)) throw new Error(`The season envelope's map credit must name its holders (${holders}), not the licence alone`);
  if (typeof envelope.standard_sentence !== "string" || !envelope.standard_sentence.includes("did not validate") || !envelope.standard_sentence.includes("CC BY-SA 4.0")) {
    throw new Error("The season envelope lacks its standard sentence (preliminary, used as provided, not validated by FloodGuard), so it must not ship");
  }
  const numbers = (value, path) => (typeof value === "number" ? [path]
    : value && typeof value === "object" ? Object.entries(value).flatMap(([key, item]) => numbers(item, `${path}.${key}`)) : []);
  const stray = numbers(envelope, "season_envelope").filter((path) => !/^season_envelope\.files\.(raster|statistics|licence)\.bytes$/.test(path));
  if (stray.length > 0) throw new Error(`timeline.json holds a figure derived from product 4009: ${stray.join(", ")}`);
  const comparison = (timeline.external_checks ?? []).filter((check) => check.role === "season_envelope_plausibility");
  if (comparison.length !== 1 || comparison[0].statistics?.href !== envelope.files.statistics.href || !/not a validation/.test(comparison[0].use)
    || numbers(comparison[0], "check").join(",") !== "check.statistics.bytes") {
    throw new Error("The season-envelope comparison must name the statistics file, say it is not a validation and hold no figure");
  }
  // The envelope is a scenario layer, never the observed side of a check: the key says what the model is compared with.
  if ("observed" in comparison[0] || typeof comparison[0].compared_with !== "string" || !comparison[0].compared_with.trim()) {
    throw new Error("The season-envelope comparison must name the envelope under compared_with, never under observed");
  }
  if ((timeline.external_checks ?? []).some((check) => check.role === "independent_magnitude_check" && /4009|envelope/i.test(check.id))) {
    throw new Error("The season-envelope comparison is listed as an independent check");
  }
  const block = timeline.evidence_blocks.filter((item) => item.covers.includes("season_envelope"));
  if (block.length !== 1 || block[0].lane !== "SCN-ENV" || block[0].shown !== true || !block[0].season_window) {
    throw new Error("One SCN-ENV evidence block must cover the season envelope, marked shown, with its season window");
  }
  // Never a day observation: no layer, observation, day or VIIRS day names the envelope or one of its files.
  if (/unosat4009|4009|envelope/i.test(JSON.stringify([timeline.layers, timeline.observations, timeline.days, timeline.viirs_daily?.days ?? []]))) {
    throw new Error("The season envelope appears among the replay's dated layers or observations");
  }
  const raster = readAsset(envelope.files.raster.href);
  if (raster.toString("ascii", 1, 4) !== "PNG" || raster.readUInt32BE(16) !== timeline.hand.width || raster.readUInt32BE(20) !== timeline.hand.height
    || raster[24] !== 1 || raster[25] !== 0) {
    throw new Error("The season-envelope raster must be a 1-bit greyscale PNG on the water grid");
  }
  const document = JSON.parse(readAsset(envelope.files.statistics.href).toString("utf8"));
  for (const notice of [document.change_notice, document.comparison?.change_notice]) {
    if (typeof notice !== "string" || !notice.startsWith("Changed by FloodGuard: clipped to Mae Sai district") || /\{|\}/.test(notice)
      || !notice.includes(credit) || !notice.includes("CC BY-SA 4.0")) {
      throw new Error("The season-envelope statistics file lacks a filled change notice with the credit and the licence");
    }
  }
  if (document.lane !== "SCN-ENV" || document.not_an_observation_for_any_replay_day !== true || document.licence?.name !== "CC BY-SA 4.0"
    || document.credit !== credit || document.map_credit !== envelope.map_credit || document.generated_at !== timeline.generated_at
    || !document.source_timestamp || document.confidence !== "low" || !document.confidence_reason || !Array.isArray(document.assumptions) || document.assumptions.length === 0
    || document.raster?.sha256 !== envelope.files.raster.sha256 || document.comparison?.role !== "season_envelope_plausibility"
    || !/not a validation/.test(document.comparison?.use ?? "") || document.official_warning !== false || document.operational_status !== "non_operational") {
    throw new Error("The season-envelope statistics file lacks its lane, licence, credit, timestamps, confidence, assumptions or plausibility wording");
  }
  if (document.standard_sentence !== envelope.standard_sentence) throw new Error("The season-envelope statistics file and the manifest give different standard sentences");
  // Other inputs of the statistics file (terrain model, population grid, boundaries): each with the licence and the credit
  // the manifest's own source line gives it, and what it was used for.
  const sources = new Map(timeline.sources.map((source) => [source.id, source]));
  const otherInputs = Array.isArray(document.other_inputs) ? document.other_inputs : [];
  if (otherInputs.map((item) => item.id).join(",") !== "copernicus-dem,worldpop,cod-ab") {
    throw new Error("The season-envelope statistics file must list its other inputs: the terrain model, the population grid and the boundaries");
  }
  for (const item of otherInputs) {
    const source = sources.get(item.id);
    if (!source || item.name !== source.name || item.licence !== source.licence || item.attribution !== source.attribution || !item.used_for) {
      throw new Error(`The season-envelope statistics file gives another licence or credit for ${item.id} than the manifest's sources`);
    }
  }
  // Residents inside the envelope: two counts, each with the rule it was counted by.
  const residents = document.comparison.residents ?? {};
  for (const [count, rule] of [["residents_in_envelope", "rule"], ["residents_in_envelope_replay_rule", "replay_rule"]]) {
    if (!Number.isFinite(residents[count]) || typeof residents[rule] !== "string" || !residents[rule].trim()) {
      throw new Error(`The season-envelope statistics file must give ${count} with its rule in ${rule}`);
    }
  }
  for (const row of [...document.comparison.district, ...document.comparison.by_tambon]) {
    for (const key of ["agreement_iou", "containment_model_in_envelope", "containment_envelope_in_model"]) {
      if (!(key in row) || (row[key] !== null && !(row[key] >= 0 && row[key] <= 1))) throw new Error(`Season-envelope comparison row lacks ${key}`);
    }
  }
  if (/precision|recall|accuracy|validated|corroborat|fpps|action_class/i.test(JSON.stringify(document).replace(/unvalidated|did not validate/gi, ""))) {
    throw new Error("The season-envelope statistics file uses a word or a key the comparison does not claim");
  }
  const licence = readAsset(envelope.files.licence.href);
  const licenceText = licence.toString("utf8");
  if (licence.includes(13) || !licenceText.endsWith("\n")) throw new Error("The season-envelope licence notice must use LF line ends");
  for (const needle of ["Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)", "https://creativecommons.org/licenses/by-sa/4.0/legalcode",
    credit, document.change_notice, document.comparison.change_notice, "envelope.png", "envelope.json", "สัญญาอนุญาต"]) {
    if (!licenceText.includes(needle)) throw new Error(`The season-envelope licence notice lacks: ${needle}`);
  }
  // Both halves of the notice name every other input with its licence and its credit; the Thai half states the changes in Thai.
  const halves = licenceText.split("-".repeat(80));
  if (halves.length !== 2) throw new Error("The season-envelope licence notice must have an English and a Thai half");
  for (const half of halves) {
    for (const item of otherInputs) {
      for (const needle of [item.name, item.licence, item.attribution]) {
        if (!half.includes(needle)) throw new Error(`A half of the season-envelope licence notice lacks, for ${item.id}: ${needle}`);
      }
    }
  }
  if (!halves[1].includes("FloodGuard เปลี่ยนแปลงดังนี้: ตัดตามขอบเขตอำเภอแม่สาย") || halves[0].includes("FloodGuard เปลี่ยนแปลงดังนี้")) {
    throw new Error("The Thai half of the season-envelope licence notice must state what FloodGuard changed in Thai");
  }
  if ((timeline.exports?.files ?? []).some((file) => file.href.startsWith(envelopeFolder))) throw new Error("A season-envelope file is in the export pack");
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
// Reported depths (news, not surveyed; roadmap C-2): inline in the manifest, so they are in the precache set and offline.
// They ship only as reported facts in lane REP, with the model's figures named as scenario values and a use rule that
// denies validation and tuning.
let reportedDepthPoints = 0;
if (timeline.reported_depths) {
  const depths = timeline.reported_depths;
  const block = timeline.evidence_blocks.filter((item) => item.covers.includes("reported_depths"));
  if (depths.status !== "reported (anecdotal, not surveyed)" || depths.lane !== "REP" || !depths.use_rule?.en?.includes("never used to tune")
    || !depths.use_rule?.en?.includes("never a validation") || !depths.use_rule?.th || block.length !== 1 || block[0].lane !== "REP"
    || !block[0].scenario_fields?.includes("reported_depths.reports[].model")) {
    throw new Error("The reported depths must ship as reported facts in lane REP, never a validation and never used to tune the model");
  }
  if (!depths.reports.every((report) => (report.point !== null) === ["medium", "high"].includes(report.location_confidence)
    && report.place?.en && report.place?.th && report.depth?.statement?.th && report.source?.url?.startsWith("https://"))) {
    throw new Error("Every reported depth needs its place and paraphrase in both languages and its source, and a point only at medium or high location confidence");
  }
  reportedDepthPoints = depths.reports.filter((report) => report.point).length;
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
console.log(`Study integrity passed: ${manifest.assets.length} C2S JSON assets, ${pngs.size} previews, ${historical.assets.length + 1} historical assets, ${timelineAssets.length} Mae Sai timeline assets (${timeline.revision}, ${timelineBytes} of ${CASE_REPLAY_BUDGET_BYTES} budget bytes; ${envelopeUrls.length} of them the season envelope's, with its licence notice; ${reportedDepthPoints} reported-depth points inside the manifest), ${exportFiles.length} Mae Sai export files (${exportBytes} of ${CASE_REPLAY_EXPORT_BUDGET_BYTES} export-budget bytes, outside the precache budget) and ${entries.length} byte-identical Git blobs.`);
