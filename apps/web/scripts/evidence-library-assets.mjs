import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const PRIVATE_KEYS = /^(?:password|access_token|refresh_token|api_key|coordinator_name|coordinator_phone|telephone|phone|phone_number|contact:phone|email|contact:email|absolute_file_path|local_path|raw_rows|raw_records|raw_observations|station_observations|ผู้ประสานงาน|ชื่อผู้ประสานงาน|เบอร์โทร|เบอร์โทรศัพท์|หมายเลขโทรศัพท์|โทรศัพท์)$/iu;
const MAX_DOWNLOAD_BYTES = 80 * 1024 * 1024;
const GZIP_AUDITOR = fileURLToPath(new URL("./evidence-gzip-json-audit.mjs", import.meta.url));
const HTML_ENTITY = /&(?:(?:quot|amp);?|(?:apos|colon|sol|bsol|lowbar|period|tab|newline);)/giu;
const NAMED_ENTITIES = { quot: '"', apos: "'", amp: "&", colon: ":", sol: "/", bsol: "\\", lowbar: "_", period: ".", tab: "\t", newline: "\n" };

function decodeHtmlEntities(value) {
  let decoded = value;
  for (let pass = 0; pass < 8; pass += 1) {
    // Numeric references have many valid semicolonless forms. Published text
    // does not need them, so reject the marker instead of guessing HTML5 rules.
    if (decoded.includes("&#")) throw new Error("Numeric HTML entity in published evidence.");
    const next = decoded.replace(HTML_ENTITY, (entity) => {
      const body = entity.slice(1).replace(/;$/u, "").toLowerCase();
      return NAMED_ENTITIES[body];
    });
    if (next === decoded) return decoded;
    decoded = next;
  }
  if (decoded.includes("&#")) throw new Error("Numeric HTML entity in published evidence.");
  HTML_ENTITY.lastIndex = 0;
  if (HTML_ENTITY.test(decoded)) throw new Error("Nested HTML entity exceeds publication audit limit.");
  return decoded;
}

export function assertPublicEvidenceKey(key) {
  if (PRIVATE_KEYS.test(key)) throw new Error(`Private/raw field in published evidence: ${key}`);
}

/** Defense in depth after the Python export's explicit field projection. */
export function assertPublicEvidenceText(value) {
  const serialized = typeof value === "string" ? value : JSON.stringify(value);
  const decoded = decodeHtmlEntities(serialized);
  if (/(?<![A-Za-z])[A-Za-z]:[\\/]|file:\/\/|(?:^|["'\s])\\{2,}[A-Za-z0-9]|\/(?:Users|home)\//iu.test(decoded)) throw new Error("Local filesystem path in published evidence.");
  for (const match of decoded.matchAll(/"([^"\n]+)"\s*:/gu)) {
    assertPublicEvidenceKey(match[1]);
  }
}

/** Only catalog-bound, publication-cleared evidence enters the competition cache. */
export function collectEvidenceLibraryAssets(out) {
  const root = resolve(out, "evidence-library");
  const catalogPath = resolve(root, "catalog.json");
  if (!existsSync(catalogPath)) throw new Error("Evidence-library catalog is missing from the competition export.");
  const urls = new Set(["/evidence-library/catalog.json"]);
  const catalog = JSON.parse(readFileSync(catalogPath, "utf8"));
  assertPublicEvidenceText(catalog);
  if (catalog.non_operational !== true || !Array.isArray(catalog.packages) || !Array.isArray(catalog.datasets)) {
    throw new Error("Invalid evidence-library catalog boundary.");
  }
  const auditedDownloads = new Set();
  function asset(url) {
    if (typeof url !== "string" || !/^\/evidence-library\/[A-Za-z0-9_/-]+\.(?:json(?:\.gz)?|geojson|md|html|txt|csv|pdf|png|webp)$/.test(url)
      || url.includes("..") || url.includes("//")) throw new Error(`Invalid evidence-library URL: ${url}`);
    const path = resolve(out, url.slice(1));
    if (!path.startsWith(`${root}${sep}`) || !existsSync(path) || !statSync(path).isFile()) throw new Error(`Missing evidence-library asset: ${url}`);
    urls.add(url);
    return path;
  }
  for (const reference of catalog.packages) {
    const path = asset(reference.url);
    const bytes = readFileSync(path);
    if (createHash("sha256").update(bytes).digest("hex") !== reference.sha256) throw new Error(`Evidence package hash mismatch: ${reference.id}`);
    const data = JSON.parse(bytes.toString("utf8"));
    assertPublicEvidenceText(data);
    if (data.id !== reference.id || data.package_version !== catalog.package_version || data.aoi_id !== reference.aoi_id || data.event_id !== reference.event_id
      || data.dataset_mode !== "candidate" || data.official_warning !== false || data.operational_status !== "non_operational"
      || data.assessment?.fpps !== null || data.assessment?.action_class !== null) throw new Error(`Invalid evidence package boundary: ${reference.id}`);
    if (data.report_url !== null) assertPublicEvidenceText(readFileSync(asset(data.report_url), "utf8"));
    for (const download of data.downloads ?? []) {
      const archivePath = asset(download.url);
      if (statSync(archivePath).size > MAX_DOWNLOAD_BYTES) throw new Error(`Evidence download exceeds 80 MiB: ${download.url}`);
      const archive = readFileSync(archivePath);
      if (createHash("sha256").update(archive).digest("hex") !== download.sha256) throw new Error(`Evidence download hash mismatch: ${download.url}`);
      if (auditedDownloads.has(download.url)) continue;
      if (download.url.endsWith(".json.gz")) {
        const result = spawnSync(process.execPath, [GZIP_AUDITOR, archivePath], {
          encoding: "utf8", maxBuffer: 64 * 1024, timeout: 10 * 60 * 1000,
        });
        if (result.error || result.status !== 0) {
          throw new Error(`Evidence gzip JSON audit failed: ${download.url}: ${result.error?.message ?? result.stderr?.trim() ?? "unknown error"}`);
        }
      } else if (download.url.endsWith(".json")) assertPublicEvidenceText(JSON.parse(archive.toString("utf8")));
      else assertPublicEvidenceText(archive.toString("utf8"));
      auditedDownloads.add(download.url);
    }
    for (const layer of data.layers ?? []) {
      if (layer.data || layer.image_url) {
        const source = catalog.datasets.find((item) => item.id === layer.dataset_id);
        if (source?.rights?.public_derivatives !== true || !["available", "partial"].includes(layer.availability)) {
          throw new Error(`Uncleared evidence derivative in ${reference.id}: ${layer.id}`);
        }
      }
      if (layer.image_url) asset(layer.image_url);
    }
  }
  function audit(directory) {
    for (const name of readdirSync(directory)) {
      const path = resolve(directory, name);
      if (statSync(path).isDirectory()) audit(path);
      else {
        const url = `/${relative(out, path).split(sep).join("/")}`;
        if (!urls.has(url)) throw new Error(`Unlisted evidence asset would be published: ${url}`);
      }
    }
  }
  audit(root);
  return [...urls].sort();
}
