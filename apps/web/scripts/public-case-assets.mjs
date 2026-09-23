import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { relative, resolve, sep } from "node:path";
import { assertPublicEvidenceText } from "./evidence-library-assets.mjs";

/** Include only checksum-bound, allowlisted case projections in the competition cache. */
export function collectPublicCaseAssets(out) {
  const root = resolve(out, "public-case-projections");
  const catalogPath = resolve(root, "catalog.json");
  if (!existsSync(catalogPath)) throw new Error("Public case projection catalog is missing.");
  const catalog = JSON.parse(readFileSync(catalogPath, "utf8"));
  assertPublicEvidenceText(catalog);
  if (catalog.schema_version !== "floodguard.public_case_catalog.v1" || !Array.isArray(catalog.packages)
    || !catalog.packages.length || !/^[a-f0-9]{64}$/.test(catalog.source_catalog_sha256 ?? "")) {
    throw new Error("Invalid public case projection catalog.");
  }
  const sourceCatalogBytes = readFileSync(resolve(out, "evidence-library", "catalog.json"));
  if (sha256(sourceCatalogBytes) !== catalog.source_catalog_sha256) throw new Error("Public case projections are bound to another evidence catalog.");
  const sourceCatalog = JSON.parse(sourceCatalogBytes.toString("utf8"));
  if (catalog.package_version !== sourceCatalog.package_version) throw new Error("Public case projection version mismatch.");
  const urls = new Set(["/public-case-projections/catalog.json"]);
  const pairs = new Set();
  for (const reference of catalog.packages) {
    const pair = `${reference.aoi_id}/${reference.event_id}`;
    if (pairs.has(pair) || !/^[A-Za-z0-9_-]+$/.test(reference.id ?? "")
      || reference.url !== `/public-case-projections/cases/${reference.id}.json`) {
      throw new Error(`Invalid or duplicate public case reference: ${reference.id}`);
    }
    pairs.add(pair);
    const source = sourceCatalog.packages.find((item) => item.id === reference.id && item.aoi_id === reference.aoi_id && item.event_id === reference.event_id);
    if (!source || source.sha256 !== reference.source_package_sha256
      || source.url !== `/evidence-library/packages/${reference.id}.json`) throw new Error(`Source package binding mismatch: ${reference.id}`);
    const sourceBytes = readFileSync(resolve(out, source.url.slice(1)));
    if (sha256(sourceBytes) !== reference.source_package_sha256) throw new Error(`Source package hash mismatch: ${reference.id}`);
    const sourcePackage = JSON.parse(sourceBytes.toString("utf8"));
    const path = resolve(out, reference.url.slice(1));
    if (!path.startsWith(`${root}${sep}`) || !existsSync(path) || !statSync(path).isFile()) throw new Error(`Missing public case projection: ${reference.url}`);
    const bytes = readFileSync(path);
    if (sha256(bytes) !== reference.sha256) throw new Error(`Public case projection hash mismatch: ${reference.id}`);
    const projected = JSON.parse(bytes.toString("utf8"));
    assertPublicEvidenceText(projected);
    if (projected.schema_version !== "floodguard.public_case.v1" || projected.package_version !== catalog.package_version
      || projected.id !== reference.id || projected.aoi_id !== reference.aoi_id || projected.event_id !== reference.event_id
      || projected.source_package_sha256 !== reference.source_package_sha256 || projected.dataset_mode !== "candidate"
      || projected.operational_status !== "non_operational" || projected.official_warning !== false
      || projected.fpps !== null || projected.action_class !== null || projected.affected_population !== null
      || projected.access !== null || projected.generated_at !== sourcePackage.generated_at
      || projected.source_analysis_generated_at !== (sourcePackage.decision_brief?.finals_analysis?.generated_at ?? null)) {
      throw new Error(`Unsafe public case projection: ${reference.id}`);
    }
    const mainRoad = Array.isArray(projected.services)
      ? projected.services.filter((service) => service?.id === "main_road") : [];
    if (mainRoad.length !== 1 || mainRoad[0].status !== "unavailable"
      || typeof mainRoad[0].reason !== "string" || !mainRoad[0].reason || mainRoad[0].facilities !== null
      || !Array.isArray(mainRoad[0].variants) || mainRoad[0].variants.length !== 0) {
      throw new Error(`Unqualified main-road access cannot carry a result: ${reference.id}`);
    }
    urls.add(reference.url);
  }
  for (const path of walk(root)) {
    const url = `/${relative(out, path).split(sep).join("/")}`;
    if (!urls.has(url)) throw new Error(`Unlisted public case asset would be published: ${url}`);
  }
  return [...urls].sort();
}

function sha256(bytes) { return createHash("sha256").update(bytes).digest("hex"); }
function walk(directory) {
  return readdirSync(directory).flatMap((name) => {
    const path = resolve(directory, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}
