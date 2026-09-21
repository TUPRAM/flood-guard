import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { relative, resolve, sep } from "node:path";
import { gunzipSync } from "node:zlib";

const PRIVATE_KEYS = /^(?:password|access_token|refresh_token|api_key|coordinator_name|coordinator_phone|telephone|phone|phone_number|contact:phone|email|contact:email|absolute_file_path|local_path|raw_rows|raw_records|raw_observations|station_observations|ผู้ประสานงาน|ชื่อผู้ประสานงาน|เบอร์โทร|เบอร์โทรศัพท์|หมายเลขโทรศัพท์|โทรศัพท์)$/iu;

/** Defense in depth after the Python export's explicit field projection. */
export function assertPublicEvidenceText(value) {
  const serialized = typeof value === "string" ? value : JSON.stringify(value);
  const decoded = serialized.replaceAll("&quot;", '"').replaceAll("&#x27;", "'").replaceAll("&amp;", "&");
  if (/(?<![A-Za-z])[A-Za-z]:[\\/]|file:\/\/|(?:^|["'\s])\\{2,}[A-Za-z0-9]|\/(?:Users|home)\//iu.test(decoded)) throw new Error("Local filesystem path in published evidence.");
  for (const match of decoded.matchAll(/"([^"\n]+)"\s*:/gu)) {
    if (PRIVATE_KEYS.test(match[1])) throw new Error(`Private/raw field in published evidence: ${match[1]}`);
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
      if (statSync(archivePath).size > 50 * 1024 * 1024) throw new Error(`Evidence download exceeds 50 MiB: ${download.url}`);
      const archive = readFileSync(archivePath);
      if (createHash("sha256").update(archive).digest("hex") !== download.sha256) throw new Error(`Evidence download hash mismatch: ${download.url}`);
      const content = download.url.endsWith(".json.gz") ? gunzipSync(archive, { maxOutputLength: 256 * 1024 * 1024 }) : archive;
      if (download.url.endsWith(".json.gz") || download.url.endsWith(".json")) assertPublicEvidenceText(JSON.parse(content.toString("utf8")));
      else assertPublicEvidenceText(content.toString("utf8"));
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
