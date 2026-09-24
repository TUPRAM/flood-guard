import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, resolve } from "node:path";
import assert from "node:assert/strict";
import test from "node:test";
import { assertBriefRights, auditExistingBriefs, buildCaseBriefs, loadBriefSource, renderCaseHtml, validateBriefCase } from "./build-case-briefs.mjs";

const publicRoot = resolve(import.meta.dirname, "..", "public");
const manifest = JSON.parse(readFileSync(resolve(publicRoot, "briefs", "catalog.json"), "utf8"));
const source = loadBriefSource(publicRoot, manifest.source_projection_catalog_sha256);
const hash = (value) => createHash("sha256").update(value).digest("hex");
const clone = (value) => structuredClone(value);

test("brief catalog is byte-bound to the current projection and every one-page download", () => {
  assert.equal(manifest.schema_version, "floodguard.case_briefs.v1");
  assert.equal(manifest.profile, "competition");
  assert.equal(manifest.source_evidence_catalog_sha256, source.catalog.source_catalog_sha256);
  assert.equal(manifest.package_version, source.catalog.package_version);
  assert.equal(manifest.briefs.length, source.cases.length);
  for (const item of source.cases) {
    const entry = manifest.briefs.find((brief) => brief.id === item.reference.id);
    assert.ok(entry);
    assert.equal(entry.source_projection_sha256, item.reference.sha256);
    assert.equal(entry.source_package_sha256, item.reference.source_package_sha256);
    for (const [url, digest] of [[entry.html_url, entry.html_sha256], [entry.pdf_url, entry.pdf_sha256]]) {
      assert.match(url, new RegExp(`^/briefs/${item.reference.id}\\.(?:html|pdf)$`));
      assert.equal(hash(readFileSync(resolve(publicRoot, url.slice(1)))), digest);
    }
    const html = readFileSync(resolve(publicRoot, entry.html_url.slice(1)), "utf8");
    const pdf = readFileSync(resolve(publicRoot, entry.pdf_url.slice(1)));
    assert.match(html, /data-dataset-mode="candidate"/);
    assert.match(html, /data-official-warning="false"/);
    assert.match(html, /data-accepted-fpps="unavailable"/);
    assert.ok(html.includes(`data-source-projection-sha256="${item.reference.sha256}"`));
    assert.ok(html.includes(`data-source-analysis-generated-at="${item.projected.source_analysis_generated_at ?? "unavailable"}"`));
    assert.ok(html.includes(`data-package-release-generated-at="${item.projected.generated_at}"`));
    assert.ok(html.includes(item.reference.source_package_sha256));
    assert.ok(html.includes(item.aoi.name_th));
    assert.match(html, /Main-road access has no separately qualified service result/);
    assert.match(html, /การเข้าถึงถนนสายหลักยังไม่มีผลบริการแยก/);
    assert.equal((pdf.toString("latin1").match(/\/Type\s*\/Page\b/g) ?? []).length, 1);
  }
});

test("rendered case-specific copy distinguishes a modelled closure from missing data", () => {
  const maeSai = source.cases.find((item) => item.reference.id === "aoi-01_mae_sai_core_mae_sai_2024");
  const district = source.cases.find((item) => !item.projected.services.some((service) => service.id === "hospital"
    && service.variants.some((variant) => variant.travel_mode === "walking")));
  assert.ok(maeSai && district);
  const hospitalWalking = maeSai.projected.services.find((service) => service.id === "hospital")
    ?.variants.find((variant) => variant.travel_mode === "walking");
  assert.ok(hospitalWalking?.candidate_flood_scenario_id);
  const loss = Math.round(hospitalWalking.candidate_flood_losing_30_min_access).toLocaleString("en-US");
  const maeHtml = renderCaseHtml(maeSai, source);
  const districtHtml = renderCaseHtml(district, source);
  assert.ok(maeHtml.includes(`about ${loss} residents lose 30-minute hospital access`));
  assert.match(maeHtml, /road closure is an assumption, not an observed closure/);
  assert.ok(maeHtml.includes(`ประชากรราว ${loss} คนจะเสียการเข้าถึงโรงพยาบาล`));
  assert.match(districtHtml, /No eligible service\/mode comparison is available/);
  assert.match(districtHtml, /Missing access is unknown, not zero/);
  assert.ok(!districtHtml.includes(`about ${loss} residents lose 30-minute hospital access`));
  const lower = source.cases.find((item) => item.reference.aoi_id.startsWith("aoi-05"));
  assert.ok(lower);
  const lowerHtml = renderCaseHtml(lower, source);
  assert.match(lowerHtml, /2024 and 2025 selections share one static access baseline/);
  assert.match(lowerHtml, /routing uses a 10 km AOI buffer while resident demand and reporting stay in AOI intersections/);
  assert.match(lowerHtml, /การหาเส้นทางใช้พื้นที่กันชน 10 กม. รอบ AOI/);
});

test("brief case validation rejects accepted-looking, mixed and missing-as-zero values", () => {
  const item = source.cases[0];
  const validate = (mutate, expected) => {
    const candidate = clone(item.projected);
    mutate(candidate);
    assert.throws(() => validateBriefCase(candidate, item.reference, source.catalog.package_version), expected);
  };
  validate((value) => { value.fpps = 0; }, /Accepted-looking/);
  validate((value) => { value.action_class = "E"; }, /Accepted-looking/);
  validate((value) => { value.affected_population = 0; }, /Accepted-looking/);
  validate((value) => { value.demographic_equity_status = "available"; }, /Accepted-looking/);
  validate((value) => { value.private_rows = []; }, /unapproved fields/);
  validate((value) => { value.services[0].variants[0].candidate_flood_newly_unreachable_population = null; }, /Partial scenario/);
  validate((value) => { value.services[0].variants[0].unknown_access_population = -1; }, /finite nonnegative/);
  validate((value) => { value.package_version = "stale"; }, /Case identity mismatch/);
});

test("brief rights require every derived input and candidate SAR purpose", () => {
  const catalog = JSON.parse(readFileSync(resolve(publicRoot, "evidence-library", "catalog.json"), "utf8"));
  const candidate = source.cases[0].projected;
  for (const id of ["context-worldpop", "context-osm", "context-admin", "project-scenarios", "context-sar-candidate"]) {
    const denied = clone(catalog);
    denied.datasets.find((item) => item.id === id).rights.public_derivatives = false;
    assert.throws(() => assertBriefRights(denied, candidate), /permission missing/);
  }
  const noFlood = source.cases.find((item) => item.reference.id === "aoi-02_mae_sai_district_mae_sai_2024").projected;
  const deniedSar = clone(catalog);
  deniedSar.datasets.find((item) => item.id === "context-sar-candidate").rights.public_derivatives = false;
  assert.doesNotThrow(() => assertBriefRights(deniedSar, noFlood));
});

test("pinned catalog and output path fail closed", async () => {
  assert.throws(() => loadBriefSource(publicRoot, "0".repeat(64)), /SHA-256 mismatch/);
  await assert.rejects(
    () => buildCaseBriefs({ publicDirectory: publicRoot, outputDirectory: resolve(publicRoot, "outside"), catalogSha256: manifest.source_projection_catalog_sha256 }),
    /allowlisted public\/briefs directory/,
  );
});

test("replacement audit protects existing generated files and refuses extras", () => {
  assert.doesNotThrow(() => auditExistingBriefs(resolve(publicRoot, "briefs")));
  const directory = mkdtempSync(resolve(tmpdir(), "floodguard-brief-audit-"));
  try {
    const html = Buffer.from("<html>candidate</html>");
    const pdf = Buffer.from("%PDF-brief-test");
    const catalog = { schema_version: "floodguard.case_briefs.v1", briefs: [{ id: "case-one",
      html_url: "/briefs/case-one.html", html_sha256: hash(html),
      pdf_url: "/briefs/case-one.pdf", pdf_sha256: hash(pdf) }] };
    writeFileSync(resolve(directory, "catalog.json"), JSON.stringify(catalog));
    writeFileSync(resolve(directory, "case-one.html"), html);
    writeFileSync(resolve(directory, "case-one.pdf"), pdf);
    assert.doesNotThrow(() => auditExistingBriefs(directory));
    writeFileSync(resolve(directory, "unlisted.txt"), "user work");
    assert.throws(() => auditExistingBriefs(directory), /unlisted brief asset/);
    rmSync(resolve(directory, "unlisted.txt"));
    writeFileSync(resolve(directory, "case-one.pdf"), "changed bytes");
    assert.throws(() => auditExistingBriefs(directory), /hash mismatch/);
  } finally {
    assert.equal(dirname(directory), resolve(tmpdir()));
    assert.ok(basename(directory).startsWith("floodguard-brief-audit-"));
    rmSync(directory, { recursive: true });
  }
});
