import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { basename, resolve } from "node:path";

// Preserve the shipped historical report without changing the Planning copy.
const root = resolve(import.meta.dirname, "../../..");
const publicRoot = resolve(root, "apps/web/public");
const prefix = "/studies/mae-sai-geoai/2026-07-30-r1";
const target = resolve(publicRoot, prefix.slice(1));
const files = new Map();
const digest = (bytes) => createHash("sha256").update(bytes).digest("hex");
const original = readFileSync(resolve(publicRoot, "geoai/mae-sai-real.json"));
const assets = [];
function freeze(value) {
  if (typeof value === "string" && value.startsWith("/geoai/") && value.endsWith(".png")) {
    const bytes = readFileSync(resolve(publicRoot, value.slice(1)));
    const sha256 = digest(bytes);
    const name = `${sha256.slice(0, 16)}-${basename(value)}`;
    files.set(name, bytes);
    const href = `${prefix}/${name}`;
    if (!assets.some((asset) => asset.href === href)) assets.push({ href, sha256, bytes: bytes.length, original_href: value });
    return href;
  }
  if (Array.isArray(value)) return value.map(freeze);
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, freeze(item)]));
  return value;
}
const report = freeze(JSON.parse(original));
const reportBytes = Buffer.from(`${JSON.stringify(report, null, 2)}\n`);
files.set("report.json", reportBytes);
for (const file of ["README.md", "geoai_metrics.json", "CHECKSUMS"]) {
  const source = resolve(root, "docs/baseline/2026-07-30-run1", file);
  const bytes = readFileSync(source);
  files.set(file, bytes);
  assets.push({ href: `${prefix}/${file}`, sha256: digest(bytes), bytes: bytes.length, original_href: `docs/baseline/2026-07-30-run1/${file}` });
}
const labelDiagnosis = readFileSync(resolve(root, "services/geoai-runner/geoai_runner/realpipeline/water_label.py"), "utf8").split('"""')[1];
const diagnosisBytes = Buffer.from(`# MNDWI label-quality diagnosis\n\n${labelDiagnosis.trim()}\n`);
files.set("label-diagnosis.md", diagnosisBytes);
assets.push({ href: `${prefix}/label-diagnosis.md`, sha256: digest(diagnosisBytes), bytes: diagnosisBytes.length, original_href: "services/geoai-runner/geoai_runner/realpipeline/water_label.py module docstring" });
const manifest = {
  study_id: "mae-sai-geoai", revision: "2026-07-30-r1", historical: true,
  data_mode: report.data_mode, source_timestamp: report.generated_at,
  run_date: "2026-07-30", run_date_source: "docs/baseline/2026-07-30-run1/README.md",
  source_timestamp_note: "The original generated_at field is the observation timestamp, not the run date.",
  licence: "Historical project report; underlying sources retain their own terms. See the source links on the archive page. No new training permission is asserted.",
  assumptions: ["Report only; cannot feed the decision layer.", "Optical U-Net scores measure OmniWaterMask teacher agreement, not Mae Sai water accuracy.", "Different inputs, labels, geography and split prevent direct comparison with C2S-MS scores."],
  can_feed_decision_layer: false,
  original_report_sha256: digest(original),
  report: { href: `${prefix}/report.json`, sha256: digest(reportBytes), bytes: reportBytes.length },
  assets,
};
files.set("manifest.json", Buffer.from(`${JSON.stringify(manifest, null, 2)}\n`));
for (const [name, bytes] of files) {
  const path = resolve(target, name);
  if (existsSync(path) && !readFileSync(path).equals(bytes)) {
    throw new Error(`Historical revision already contains different bytes: ${name}`);
  }
}
mkdirSync(target, { recursive: true });
for (const [name, bytes] of files) if (!existsSync(resolve(target, name))) writeFileSync(resolve(target, name), bytes);
console.log(`Archived historical report and ${assets.length} source/preview assets at ${prefix}`);
