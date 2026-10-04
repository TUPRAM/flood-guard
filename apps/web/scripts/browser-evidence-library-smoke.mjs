import { createReadStream, existsSync, mkdirSync, readFileSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, resolve, sep } from "node:path";
import { launchFloodGuardBrowser } from "./browser-launch.mjs";

const out = resolve(process.env.FLOODGUARD_PROFILE_OUT ?? resolve(process.cwd(), "out"));
const catalog = JSON.parse(readFileSync(resolve(out, "evidence-library", "catalog.json"), "utf8"));
const ROUTE_CASES = {
  maeSai: "aoi-01_mae_sai_core_mae_sai_2024",
  hatYai: "aoi-03_hat_yai_core_hat_yai_2025",
  lower2024: "aoi-06_chao_phraya_rangsit_chao_phraya_2024",
};
const types = { ".html": "text/html", ".js": "text/javascript", ".json": "application/json", ".css": "text/css", ".png": "image/png", ".webp": "image/webp", ".woff2": "font/woff2", ".md": "text/markdown" };
const server = createServer((request, response) => {
  const url = new URL(request.url ?? "/", "http://127.0.0.1");
  let path = resolve(out, decodeURIComponent(url.pathname).replace(/^\/+/, "") || "index.html");
  if (!path.startsWith(`${out}${sep}`) && path !== out) return response.writeHead(403).end();
  if (existsSync(path) && statSync(path).isDirectory()) path = resolve(path, "index.html");
  if (!existsSync(path) || !statSync(path).isFile()) return response.writeHead(404).end();
  response.writeHead(200, { "Content-Type": types[extname(path)] ?? "application/octet-stream", "Cache-Control": "no-store", "Service-Worker-Allowed": "/" });
  createReadStream(path).pipe(response);
});
await new Promise((done) => server.listen(0, "127.0.0.1", done));
const address = server.address();
if (!address || typeof address === "string") throw new Error("Evidence QA server did not bind.");
const origin = `http://127.0.0.1:${address.port}`;
const workspaceOnly = process.argv.includes("--workspace-only");
const sharedOnly = process.argv.includes("--shared-only");
const offlineOnly = process.argv.includes("--offline-only");
const captureArgument = process.argv.indexOf("--capture-dir");
const captureDirectory = captureArgument >= 0 && process.argv[captureArgument + 1] ? resolve(process.argv[captureArgument + 1]) : null;
if (captureDirectory) mkdirSync(captureDirectory, { recursive: true });
let routeCasesChecked = 0;
let briefCasesChecked = 0;
let sharedViewsChecked = 0;
const routeCoverageCounts = { hospital_origin_change: 0, service_mode: 0, other_case: 0, representative: 0 };
let workspaceViewportsChecked = 0;
const browser = await launchFloodGuardBrowser();
try {
  const context = await browser.newContext({ serviceWorkers: "allow", viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const errors = [];
  const invalidRequests = [];
  page.on("pageerror", (error) => errors.push(error.stack ?? error.message));
  page.on("request", (request) => { const url = new URL(request.url()); const optionalMapTile = url.protocol === "https:" && url.hostname === "tile.openstreetmap.org" && /^\/\d+\/\d+\/\d+\.png$/.test(url.pathname); if ((!optionalMapTile && url.origin !== origin) || url.pathname.startsWith("/api/")) invalidRequests.push(url.href); });
  if (sharedOnly) {
    await verifySharedViews(page, false);
    await verifyMainSurfaces(page, false);
    await page.waitForFunction(() => Boolean(navigator.serviceWorker.controller));
    await context.setOffline(true);
    await verifySharedViews(page, true);
    await verifyMainSurfaces(page, true);
  } else if (offlineOnly) {
    await page.goto(`${origin}/studio/library/`, { waitUntil: "networkidle" });
    await page.waitForFunction(() => Boolean(navigator.serviceWorker.controller));
    await context.setOffline(true);
    await verifyDecisionBrief(page, true);
    await verifySharedViews(page, true);
    await verifyMainSurfaces(page, true);
    await verifyRouteWorkspace(page);
    await verifyRouteWorkspace(page, "aoi-03_hat_yai_core");
  } else if (workspaceOnly) {
    await verifyRouteWorkspace(page);
    await verifyRouteWorkspace(page, "aoi-03_hat_yai_core");
  } else {
  await page.goto(`${origin}/studio/library/`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "Study-area evidence library" }).waitFor();
  await page.waitForFunction(() => Boolean(navigator.serviceWorker.controller));
  for (const reference of catalog.packages) {
    await page.selectOption("#evidence-case", reference.id);
    await page.locator("main[data-evidence-library] footer").filter({ hasText: reference.id }).waitFor();
    const text = await page.locator("main[data-evidence-library]").innerText();
    if (!text.includes("Primary FPPS: unavailable") || !text.includes("Action class: unavailable")) throw new Error(`Primary scoring boundary lost: ${reference.id}`);
    const alerts = page.locator("main[data-evidence-library]").getByRole("alert");
    if (await alerts.count()) throw new Error(`Evidence package has an alert: ${reference.id}: ${(await alerts.allTextContents()).join("; ")}`);
    const evidence = JSON.parse(readFileSync(resolve(out, reference.url.replace(/^\//, "")), "utf8"));
    const featureBrowser = page.locator("[data-feature-browser]");
    await featureBrowser.locator("summary").click();
    for (const layer of evidence.layers) {
      await featureBrowser.getByLabel("Table layer").selectOption(layer.id);
      if (layer.data?.features.length) {
        const total = layer.data.features.length;
        if (!(await featureBrowser.getByRole("status").innerText()).includes(`of ${total}`)) throw new Error(`Feature total is incorrect: ${reference.id}/${layer.id}`);
        if (await featureBrowser.locator("tbody tr").count() !== Math.min(total, 50)) throw new Error(`Feature table first page is incomplete: ${layer.id}`);
        if (total > 50) {
          await featureBrowser.getByRole("button", { name: "Next page" }).click();
          if (!(await featureBrowser.locator("tbody tr").first().innerText()).includes(`${layer.id}:feature:51`)) throw new Error(`Feature pagination failed: ${layer.id}`);
        }
      }
    }
    await featureBrowser.locator("summary").click();
  }
  await page.getByRole("button", { name: "ใช้ภาษาไทย" }).click();
  await page.getByRole("heading", { name: "คลังข้อมูลพื้นที่ศึกษา" }).waitFor();
  await page.getByRole("heading", { name: "ข้อมูลที่ได้และข้อจำกัด" }).waitFor();
  await page.getByRole("button", { name: "Use English" }).click();
  const report = page.getByRole("link", { name: "Download report" });
  const href = await report.getAttribute("href");
  if (!href?.startsWith("/evidence-library/")) throw new Error("Report link is not a same-origin evidence artifact.");
  const downloadPromise = page.waitForEvent("download");
  await report.click();
  const download = await downloadPromise;
  if (await download.failure()) throw new Error("Evidence report download failed.");
  await verifyDecisionBrief(page, false);
  await verifySharedViews(page, false);
  await verifyMainSurfaces(page, false);
  await verifyRouteWorkspace(page);
  await verifyRouteWorkspace(page, "aoi-03_hat_yai_core");

  await page.goto(`${origin}/studio/library/?aoi=unknown&event=unknown`);
  await page.getByRole("alert").filter({ hasText: "No package exists" }).waitFor();
  if (await page.getByRole("heading", { name: "Explicit scenario comparisons" }).count()) throw new Error("Invalid selection silently fell back to a different package.");
  const reference = catalog.packages[0];
  await page.goto(`${origin}/studio/library/?aoi=${encodeURIComponent(reference.aoi_id)}&event=${encodeURIComponent(reference.event_id)}`);
  await page.locator("main[data-evidence-library] footer").filter({ hasText: reference.id }).waitFor();
  await context.setOffline(true);
  await page.reload();
  await page.locator("main[data-evidence-library] footer").filter({ hasText: reference.id }).waitFor();
  for (const item of catalog.packages) {
    await page.selectOption("#evidence-case", item.id);
    await page.locator("main[data-evidence-library] footer").filter({ hasText: item.id }).waitFor();
  }
  await verifyDecisionBrief(page, true);
  await verifySharedViews(page, true);
  await verifyMainSurfaces(page, true);
  await page.setViewportSize({ width: 390, height: 844 });
  if (await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)) throw new Error("Evidence library overflows the mobile viewport.");
  }
  if (errors.length) throw new Error(`Browser errors: ${errors.join("; ")}`);
  if (invalidRequests.length) throw new Error(`Unexpected browser requests: ${invalidRequests.join("; ")}`);
  if (sharedOnly && sharedViewsChecked !== catalog.packages.length * 2 * 2) {
    throw new Error(`Incomplete shared-view coverage: ${sharedViewsChecked}`);
  }
  if (!sharedOnly && !workspaceOnly) {
    const networkStates = offlineOnly ? 1 : 2;
    const expectedBriefs = catalog.packages.length * 2 * 2 * networkStates;
    const expectedShared = catalog.packages.length * 2 * networkStates;
    if (briefCasesChecked !== expectedBriefs || sharedViewsChecked !== expectedShared) {
      throw new Error(`Incomplete case coverage: ${briefCasesChecked}/${expectedBriefs} briefs, ${sharedViewsChecked}/${expectedShared} shared views`);
    }
    if (!offlineOnly && (routeCoverageCounts.hospital_origin_change !== 16 || routeCoverageCounts.service_mode !== 7
      || routeCoverageCounts.other_case !== 3 || routeCoverageCounts.representative !== 7 || routeCasesChecked !== 33)) {
      throw new Error(`Incomplete bounded route coverage: ${JSON.stringify(routeCoverageCounts)}, total ${routeCasesChecked}`);
    }
    if (offlineOnly && (routeCoverageCounts.representative !== 4 || routeCasesChecked !== 4)) {
      throw new Error(`Incomplete offline route coverage: ${JSON.stringify(routeCoverageCounts)}, total ${routeCasesChecked}`);
    }
  }
  console.log(sharedOnly ? `Shared views browser: ${sharedViewsChecked} case/language/network selections; links for service-result cases passed.` : offlineOnly ? `Offline decision brief browser: ${briefCasesChecked} case/language/viewport/network selections, ${routeCasesChecked} exact route comparisons (${JSON.stringify(routeCoverageCounts)}), and ${workspaceViewportsChecked} workspace language/viewport combinations passed.` : workspaceOnly ? `Route workspace browser: ${workspaceViewportsChecked} language/viewport combinations; visible controls, map, results, accessible detail dialogs and no API requests passed.` : `Evidence browser: ${briefCasesChecked} brief case/language/viewport/network selections, ${sharedViewsChecked} shared-view selections (role links for service-result cases), and ${routeCasesChecked} bounded exact route checks (${JSON.stringify(routeCoverageCounts)}); ${workspaceViewportsChecked} workspace language/viewport combinations, keyboard/details, report download, invalid links, and no unexpected requests passed.`);
  await context.close();
} finally {
  await browser.close();
  await new Promise((done) => server.close(done));
}

async function verifySharedViews(page, offline) {
  for (const th of [false, true]) {
    for (const reference of catalog.packages) {
      const query = `aoi=${reference.aoi_id}&event=${reference.event_id}`;
      await page.goto(`${origin}/public-cases/?${query}`, { waitUntil: "domcontentloaded" });
      const toggle = page.getByRole("button", { name: th ? "ใช้ภาษาไทย" : "Use English", exact: true });
      if (await toggle.count()) await toggle.click();
      await page.locator("main[data-evidence-library] footer").filter({ hasText: reference.id }).waitFor();
      const caseSelect = page.getByRole("combobox", { name: th ? "พื้นที่ศึกษา — เหตุการณ์" : "Study area — Event", exact: true });
      const choices = await caseSelect.locator("option").evaluateAll((options) => options.map((option) => option.value));
      if (JSON.stringify(choices) !== JSON.stringify(catalog.packages.map((item) => item.id))) throw new Error("Study selector includes an unpublished area/event combination");
      const alternative = catalog.packages.find((item) => item.id !== reference.id);
      if (alternative) {
        await caseSelect.selectOption(alternative.id);
        await page.locator("main[data-evidence-library] footer").filter({ hasText: alternative.id }).waitFor();
        await caseSelect.selectOption(reference.id);
        await page.locator("main[data-evidence-library] footer").filter({ hasText: reference.id }).waitFor();
        const selectedUrl = new URL(page.url());
        if (selectedUrl.searchParams.get("aoi") !== reference.aoi_id || selectedUrl.searchParams.get("event") !== reference.event_id) throw new Error("Combined selection did not preserve its area/event deep link");
      }
      const pkg = JSON.parse(readFileSync(resolve(out, reference.url.replace(/^\//, "")), "utf8"));
      const summary = page.locator("[data-public-case-summary]");
      if (pkg.decision_brief?.finals_analysis) {
        await summary.waitFor();
        const link = summary.getByRole("link", { name: th ? "ดูแผนที่เส้นทางก่อน/หลัง" : "View before/after route map", exact: true });
        const href = await link.getAttribute("href");
        if (!href?.includes(query)) throw new Error("Public case link substituted another AOI/event");
        await summary.getByRole("combobox", { name: th ? "บริการ" : "Service", exact: true }).selectOption("pharmacy");
        await summary.getByRole("combobox", { name: th ? "การเดินทาง" : "Travel mode", exact: true }).selectOption("modelled_vehicle");
        const selectedVariant = pkg.decision_brief.finals_analysis.services.find((item) => item.id === "pharmacy")?.variants.find((item) => item.travel_mode === "modelled_vehicle" && item.speed_factor === 1);
        if (!selectedVariant) throw new Error(`Pharmacy vehicle result missing: ${reference.id}`);
        const modelledCount = selectedVariant.baseline.within_30_minutes_population.toLocaleString(th ? "th-TH" : "en-GB", { maximumFractionDigits: 0 });
        if (!(await summary.innerText()).includes(modelledCount)) throw new Error(`Public case number differs from package: ${reference.id}`);
        const mainNav = page.getByRole("navigation", { name: th ? "พื้นที่หลัก" : "Main areas" });
        const command = mainNav.getByRole("link", { name: th ? "การวางแผน" : "Planning", exact: true });
        if (!(await command.getAttribute("href"))?.includes("service=pharmacy&mode=modelled_vehicle")) throw new Error("Shared view lost service/mode");
        const studioLink = mainNav.getByRole("link", { name: th ? "หลักฐาน" : "Studio", exact: true });
        if (!(await studioLink.getAttribute("href"))?.includes(`${query}&version=${pkg.package_version}&service=pharmacy&mode=modelled_vehicle`)) throw new Error("Public-to-Studio link lost case and selection identity");
        await command.click();
        const main = page.locator('[data-shared-case="planning"]');
        await page.locator(`[data-shared-case="planning"][data-case-id="${reference.id}"]`).waitFor();
        if (await main.getByRole("combobox", { name: th ? "บริการ" : "Service", exact: true }).inputValue() !== "pharmacy") throw new Error("Planning did not retain selected service");
        if (await main.getByRole("combobox", { name: th ? "วิธีเดินทาง" : "Travel mode", exact: true }).inputValue() !== "modelled_vehicle") throw new Error("Planning did not retain selected mode");
        if (!(await page.locator(`[data-planning-candidate="${reference.id}"]`).innerText()).includes(modelledCount)) throw new Error(`Planning case number differs from Public: ${reference.id}`);
        if (!(await main.getByRole("navigation", { name: th ? "พื้นที่หลัก" : "Main areas" }).getByRole("link", { name: th ? "หลักฐาน" : "Studio" }).getAttribute("href"))?.includes(`${query}&version=${pkg.package_version}&service=pharmacy&mode=modelled_vehicle`)) throw new Error("Planning-to-Studio link lost case and selection identity");
        await page.goto(`${origin}/command/cases/?${query}&service=pharmacy&mode=modelled_vehicle`, { waitUntil: "domcontentloaded" });
        const brief = page.locator("[data-decision-brief]");
        await brief.locator("[data-finals-analysis]").waitFor();
        if (await brief.getByRole("combobox", { name: th ? "บริการที่ต้องการ" : "Service needed", exact: true }).inputValue() !== "pharmacy") throw new Error("Command did not retain selected service");
        if (await brief.getByRole("combobox", { name: th ? "วิธีเดินทางตามแบบจำลอง" : "Modelled travel mode", exact: true }).inputValue() !== "modelled_vehicle") throw new Error("Command did not retain selected mode");
      } else if (await summary.count()) throw new Error("Context AOI received a substituted result");
      const alerts = page.locator("main[data-evidence-library]").getByRole("alert");
      if (await alerts.count()) throw new Error(`Shared-view alert: ${reference.id}, offline=${offline}: ${JSON.stringify(await alerts.allTextContents())}`);
      sharedViewsChecked += 1;
    }
  }
}

async function verifyMainSurfaces(page, offline) {
  const reference = catalog.packages[0];
  const projectedCatalog = JSON.parse(readFileSync(resolve(out, "public-case-projections", "catalog.json"), "utf8"));
  const projectionReference = projectedCatalog.packages.find((item) => item.id === reference.id);
  const projection = JSON.parse(readFileSync(resolve(out, projectionReference.url.slice(1)), "utf8"));
  const projectedVariant = projection.services.find((item) => item.id === "hospital").variants.find((item) => item.travel_mode === "walking");
  const query = "aoi=" + reference.aoi_id + "&event=" + reference.event_id + "&version=" + catalog.package_version
    + "&service=hospital&mode=walking&scenario=" + projectedVariant.candidate_flood_scenario_id;
  await page.goto(origin + "/public/?" + query, { waitUntil: "domcontentloaded" });
  if (await page.evaluate(() => document.documentElement.lang) === "th") await page.getByRole("button", { name: "Use English", exact: true }).click();
  const researchLink = page.locator(".public-home-research-link");
  await researchLink.waitFor();
  if (!(await researchLink.getAttribute("href"))?.includes(query)) throw new Error("Public home research link lost the selected case or scenario");
  await researchLink.click();
  const publicSummary = page.locator("[data-public-case-summary]");
  await publicSummary.waitFor();
  const pkg = JSON.parse(readFileSync(resolve(out, reference.url.replace(/^\//, "")), "utf8"));
  const baseline = pkg.decision_brief.finals_analysis.services.find((item) => item.id === "hospital").variants.find((item) => item.travel_mode === "walking" && item.speed_factor === 1).baseline;
  const count = baseline.within_30_minutes_population.toLocaleString("en-GB", { maximumFractionDigits: 0 });
  const publicText = await publicSummary.innerText();
  if (!publicText.includes(count) || !publicText.includes("Accepted FPPS / action class: unavailable")) {
    throw new Error("Public study case differs from its package: " + reference.id + ", offline=" + offline + ", expected baseline=" + count + ", visible=" + publicText.slice(0, 900));
  }
  if (!(await publicSummary.getByRole("link", { name: "View before/after route map" }).getAttribute("href"))?.includes("scenario=" + projectedVariant.candidate_flood_scenario_id)) {
    throw new Error("Public route link lost the selected scenario");
  }
  const language = await page.evaluate(() => document.documentElement.lang);
  await page.getByRole("navigation", { name: "Main areas" }).getByRole("link", { name: "Planning" }).click();
  const planning = page.locator('[data-shared-case="planning"]');
  await page.locator('[data-shared-case="planning"][data-case-id="' + reference.id + '"]').waitFor();
  const overview = page.locator('[data-planning-candidate="' + reference.id + '"]');
  await overview.waitFor();
  if (await page.evaluate(() => document.documentElement.lang) !== language) throw new Error("Language preference changed on Public to Planning transition");
  if (await planning.getByRole("combobox", { name: "Service", exact: true }).inputValue() !== "hospital") throw new Error("Planning lost Public service choice");
  if (await planning.getByRole("combobox", { name: "Travel mode", exact: true }).inputValue() !== "walking") throw new Error("Planning lost Public mode choice");
  if (!(await overview.innerText()).includes(count) || !(await overview.innerText()).includes("Accepted FPPS and action class remain unavailable")) {
    throw new Error("Planning result or acceptance boundary differs from Public");
  }
  if (new URL(page.url()).searchParams.get("scenario") !== projectedVariant.candidate_flood_scenario_id) throw new Error("Planning lost the Public scenario");
  await planning.getByRole("navigation", { name: "Main areas" }).getByRole("link", { name: "Studio" }).click();
  const studio = page.locator('[data-shared-case="studio"]');
  await page.locator('[data-shared-case="studio"][data-case-id="' + reference.id + '"]').waitFor();
  const report = page.locator('[data-evidence-case-id="' + reference.id + '"]');
  await report.waitFor();
  if (await page.evaluate(() => document.documentElement.lang) !== language) throw new Error("Language preference changed on Planning to Studio transition");
  if (!(await report.innerText()).includes("Accepted FPPS / action class")) throw new Error("Studio report lost the downstream acceptance boundary");
  const selected = new URL(page.url());
  if (selected.searchParams.get("aoi") !== reference.aoi_id || selected.searchParams.get("event") !== reference.event_id
    || selected.searchParams.get("version") !== catalog.package_version
    || selected.searchParams.get("service") !== "hospital" || selected.searchParams.get("mode") !== "walking"
    || selected.searchParams.get("scenario") !== projectedVariant.candidate_flood_scenario_id || await studio.getByRole("alert").count()) {
    throw new Error("Main-surface deep link lost case or scenario identity");
  }
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.locator('[data-evidence-case-id="' + reference.id + '"]').waitFor();
  if (new URL(page.url()).searchParams.get("scenario") !== projectedVariant.candidate_flood_scenario_id) throw new Error("Studio reload lost the scenario");
  await page.getByRole("button", { name: "ใช้ภาษาไทย", exact: true }).click();
  await page.locator('[data-shared-case="studio"]').getByRole("navigation", { name: "พื้นที่หลัก" }).getByRole("link", { name: "ประชาชน" }).click();
  if (await page.evaluate(() => document.documentElement.lang) !== "th") throw new Error("Thai preference was lost on Studio to Public transition");
  await page.setViewportSize({ width: 390, height: 844 });
  if (await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)) throw new Error("Main Public page overflows the mobile viewport");
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole("button", { name: "Use English", exact: true }).click();
  await verifyRoleUrlSynchronization(page);
  await page.goto(origin + "/public/?aoi=unknown&event=unknown", { waitUntil: "domcontentloaded" });
  await page.locator(".public-home-research-link").click();
  await page.locator("main[data-evidence-library]").getByRole("alert").filter({ hasText: "Another area's data will not be substituted" }).waitFor();
  if (await page.locator("[data-public-case-summary]").count()) throw new Error("Unknown Public case displayed another case");
  for (const [path, role, lowerSelector] of [
    ["/command/", "planning", "[data-planning-candidate]"],
    ["/studio/", "studio", "[data-evidence-case-id]"],
  ]) {
    await page.goto(origin + path + "?aoi=unknown&event=unknown", { waitUntil: "domcontentloaded" });
    const card = page.locator('[data-shared-case="' + role + '"]');
    await card.getByRole("alert").filter({ hasText: "Another case is not substituted" }).waitFor();
    const lower = page.locator(lowerSelector);
    const lowerCaseId = await lower.count() ? await lower.first().getAttribute(role === "planning" ? "data-planning-candidate" : "data-evidence-case-id") : null;
    if (await card.getAttribute("data-case-id") || lowerCaseId === reference.id) {
      throw new Error("Unknown " + role + " case displayed another package");
    }
  }
}

async function verifyRoleUrlSynchronization(page) {
  const first = catalog.packages[0];
  const alternative = catalog.packages.find((item) => item.aoi_id.startsWith("aoi-03")) ?? catalog.packages[1];
  for (const [path, role, lowerSelector, detailPath] of [
    ["/command/", "planning", "[data-planning-candidate]", "/command/cases/"],
    ["/studio/", "studio", "[data-evidence-case-id]", "/studio/library/"],
  ]) {
    await page.goto(origin + path + "?aoi=" + first.aoi_id + "&event=" + first.event_id + "&version=" + catalog.package_version, { waitUntil: "domcontentloaded" });
    const top = page.locator('[data-shared-case="' + role + '"]');
    await page.locator('[data-shared-case="' + role + '"][data-case-id="' + first.id + '"]').waitFor();
    const lower = page.locator(lowerSelector);
    await lower.waitFor();
    await top.getByRole("combobox", { name: "Study area — Event", exact: true }).selectOption(alternative.id);
    await page.locator('[data-shared-case="' + role + '"][data-case-id="' + alternative.id + '"]').waitFor();
    await page.locator(lowerSelector + '[' + (role === "planning" ? "data-planning-candidate" : "data-evidence-case-id") + '="' + alternative.id + '"]').waitFor();
    const selected = new URL(page.url());
    if (selected.searchParams.get("aoi") !== alternative.aoi_id || selected.searchParams.get("event") !== alternative.event_id) {
      throw new Error(role + " case selector left a divergent URL");
    }
    if (role === "planning") {
      await top.getByRole("combobox", { name: "Service", exact: true }).selectOption("pharmacy");
      await top.getByRole("combobox", { name: "Travel mode", exact: true }).selectOption("modelled_vehicle");
      const choice = new URL(page.url());
      if (choice.searchParams.get("service") !== "pharmacy" || choice.searchParams.get("mode") !== "modelled_vehicle") {
        throw new Error("Planning service and mode did not update the URL");
      }
    }
    await page.goto(origin + detailPath + "?aoi=" + first.aoi_id + "&event=" + first.event_id + "&version=" + catalog.package_version, { waitUntil: "domcontentloaded" });
    const detail = page.locator("main[data-evidence-library]");
    await detail.locator("footer").filter({ hasText: first.id }).waitFor();
    await detail.locator("#evidence-case").selectOption(alternative.id);
    await detail.locator("footer").filter({ hasText: alternative.id }).waitFor();
    const detailSelected = new URL(page.url());
    if (detailSelected.searchParams.get("aoi") !== alternative.aoi_id || detailSelected.searchParams.get("event") !== alternative.event_id) {
      throw new Error(role + " detail selector left a divergent URL");
    }
    const archiveLink = detail.getByRole("navigation", { name: "Pages in this area" }).getByRole("link", { name: role === "planning" ? "Research archive" : "Historical report" });
    await archiveLink.click();
    const archived = new URL(page.url());
    if (archived.searchParams.get("aoi") !== alternative.aoi_id || archived.searchParams.get("event") !== alternative.event_id) {
      throw new Error(role + " archive link dropped the selected case");
    }
    await page.getByRole("link", { name: role === "planning" ? "Current planning overview" : "Open the current study-case report" }).click();
    await page.locator('[data-shared-case="' + role + '"][data-case-id="' + alternative.id + '"]').waitFor();
  }
}
// Browser coverage is bounded: all 8 case briefs at 2 widths × 2 languages ×
// online/offline; 16 hospital/walking origin-change checks in three areas;
// seven other service/mode checks, three other finals-case routes and seven
// representative Thai/mobile/offline routes. Package tests own exhaustive data.
function boundedRouteTargets(reference, analysis, viewport, th, offline) {
  const routes = analysis.routes;
  if (!routes || routes.status !== "available") return [];
  const first = (service, mode, category) => {
    const comparison = routes.comparisons.find((item) => item.service_type === service && item.travel_mode === mode && item.scenario_kind === "close_edge");
    if (!comparison) throw new Error(`Browser route matrix lacks ${reference.id}/${service}/${mode}`);
    return { service, mode, originId: comparison.origin_id, kind: comparison.scenario_kind, category };
  };
  if (!offline && !th && viewport.width === 1440) {
    const extras = {
      [ROUTE_CASES.maeSai]: [["hospital", "modelled_vehicle"], ["primary_care", "walking"], ["primary_care", "modelled_vehicle"]],
      [ROUTE_CASES.hatYai]: [["pharmacy", "walking"], ["pharmacy", "modelled_vehicle"]],
      [ROUTE_CASES.lower2024]: [["shelter", "walking"], ["shelter", "modelled_vehicle"]],
    };
    const targets = (extras[reference.id] ?? []).map(([service, mode]) => first(service, mode, "service_mode"));
    if ([ROUTE_CASES.maeSai, ROUTE_CASES.hatYai, ROUTE_CASES.lower2024].includes(reference.id)) {
      for (const origin of routes.origins) {
        for (const kind of ["close_edge", "remove_destination"]) {
          targets.push({ service: "hospital", mode: "walking", originId: origin.id, kind, category: "hospital_origin_change" });
        }
      }
    } else targets.push(first("hospital", "walking", "other_case"));
    return targets;
  }
  const context = `${viewport.width === 390 ? "mobile" : "desktop"}-${th ? "th" : "en"}-${offline ? "offline" : "online"}`;
  const representatives = {
    "desktop-th-online": ROUTE_CASES.hatYai,
    "mobile-en-online": ROUTE_CASES.lower2024,
    "mobile-th-online": ROUTE_CASES.maeSai,
    "desktop-en-offline": ROUTE_CASES.lower2024,
    "desktop-th-offline": ROUTE_CASES.maeSai,
    "mobile-en-offline": ROUTE_CASES.hatYai,
    "mobile-th-offline": ROUTE_CASES.lower2024,
  };
  return representatives[context] === reference.id ? [first("hospital", "walking", "representative")] : [];
}

async function verifyDecisionBrief(page, offline) {
  const first = catalog.packages[0];
  await page.goto(`${origin}/studio/brief/?aoi=${encodeURIComponent(first.aoi_id)}&event=${encodeURIComponent(first.event_id)}`, { waitUntil: "domcontentloaded" });
  const main = page.locator("main[data-evidence-library]");
  for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    for (const th of [false, true]) {
      const toggle = page.getByRole("button", { name: th ? "ใช้ภาษาไทย" : "Use English", exact: true });
      if (await toggle.count()) await toggle.click();
      await page.getByRole("heading", { level: 1, name: th ? /^(บทสรุปเพื่อการตัดสินใจ|เส้นทางก่อนและหลัง)$/ : /^(Study-area decision brief|Compare before & after routes)$/ }).waitFor();
      for (const reference of catalog.packages) {
        console.log(`Checking ${reference.id}, ${viewport.width}px, Thai=${th}, offline=${offline}`);
        await page.selectOption("#evidence-case", reference.id);
        await main.locator("footer").filter({ hasText: reference.id }).waitFor();
        const evidence = JSON.parse(readFileSync(resolve(out, reference.url.replace(/^\//, "")), "utf8"));
        if (!evidence.decision_brief) throw new Error(`Decision brief package missing: ${reference.id}`);
        const brief = main.locator("[data-decision-brief]");
        await brief.waitFor();
        if (await main.getByRole("alert").count()) throw new Error(`Decision brief has an alert: ${reference.id}`);
        if (evidence.decision_brief.finals_analysis) {
          const analysis = evidence.decision_brief.finals_analysis;
          await verifyFinalsComparison(page, brief, analysis, th, offline, boundedRouteTargets(reference, analysis, viewport, th, offline));
        } else if (evidence.decision_brief.access) {
          if (await brief.locator("[data-brief-intervention]").count() !== evidence.decision_brief.interventions.length) throw new Error(`Decision brief intervention count differs from selected package: ${reference.id}`);
          const year = evidence.decision_brief.population_reference_year ?? (th ? "ไม่ทราบ" : "year unknown");
          const label = th ? `ประชากรตามแบบจำลองในพื้นที่ศึกษา (ปี ${year})` : `Modelled residents in the study area (${year})`;
          const displayed = await brief.getByText(label, { exact: true }).locator("..").locator("dd").innerText();
          const expected = evidence.decision_brief.access.modelled_population.toLocaleString(th ? "th-TH" : "en-GB", { maximumFractionDigits: 1 });
          if (displayed !== expected) throw new Error(`Decision brief population differs from selected package: ${reference.id}: ${displayed} != ${expected}`);
        } else {
          await brief.getByText(th ? "พื้นที่นี้มีข้อมูลความครอบคลุม ยังไม่มีการคำนวณการเข้าถึง" : "This area has an evidence-coverage view; access calculations are unavailable.", { exact: true }).waitFor();
        }
        const evidenceDialog = evidence.decision_brief.finals_analysis ? await openFinalsDetail(brief, "evidence") : null;
        const text = await (evidenceDialog ?? brief).innerText();
        for (const boundary of th ? ["คะแนน / ระดับการดำเนินการ", "ยังไม่พร้อม", "ประชากรที่ได้รับผลจากน้ำท่วม", "ยังไม่ทราบ"] : ["FPPS / action class", "Unavailable", "Flood-affected population", "Unknown"]) {
          if (!text.includes(boundary)) throw new Error(`Decision brief lost its unknown-evidence boundary: ${reference.id}: ${boundary}`);
        }
        if (evidenceDialog && reference.id === first.id && evidence.decision_brief.finals_analysis.capacity.site_id) {
          await evidenceDialog.getByText(th ? "ความจุและความต้องการสมมติ" : "Hypothetical capacity and demand", { exact: true }).click();
          await evidenceDialog.getByText(th
            ? "ผูกตำแหน่งกับการเพิ่มจุดหมายสมมติที่ระบุ แล้วสมมติบทบาทเป็นศูนย์พักพิงแยกต่างหาก ไม่ได้เปลี่ยนโรงพยาบาลเป็นศูนย์พักพิงหรือยืนยันว่าพื้นที่ปลอดภัย"
            : "A named hypothetical access-addition location is assigned a separate shelter scenario. This does not turn a hospital into a shelter or establish site safety.", { exact: true }).waitFor();
        }
        if (evidenceDialog) await closeFinalsDetail(page, brief, "evidence");
        if (await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)) throw new Error(`Decision brief overflows ${viewport.width}px: ${reference.id}, Thai=${th}, offline=${offline}`);
        briefCasesChecked += 1;
      }
    }
  }
  await page.getByRole("button", { name: "Use English", exact: true }).click();
  await page.goto(`${origin}/studio/brief/?aoi=unknown&event=unknown`, { waitUntil: "domcontentloaded" });
  await main.getByRole("alert").filter({ hasText: "No package exists" }).waitFor();
  if (await main.locator("[data-decision-brief]").count()) throw new Error(`Invalid brief selection substituted another package, offline=${offline}`);
  await page.goto(`${origin}/studio/brief/?aoi=${encodeURIComponent(first.aoi_id)}&event=${encodeURIComponent(first.event_id)}`, { waitUntil: "domcontentloaded" });
  await main.locator("footer").filter({ hasText: first.id }).waitFor();
}

async function verifyFinalsComparison(page, brief, analysis, th, offline, routeTargets) {
  await brief.locator("[data-finals-analysis]").waitFor();
  const serviceSelect = brief.getByRole("combobox", { name: th ? "บริการที่ต้องการ" : "Service needed", exact: true });
  const modeSelect = brief.getByRole("combobox", { name: th ? "วิธีเดินทางตามแบบจำลอง" : "Modelled travel mode", exact: true });
  const routes = analysis.routes;
  const selectedPairs = new Set([`${analysis.primary_service}/walking`, ...routeTargets.map((item) => `${item.service}/${item.mode}`)]);
  for (const service of analysis.services) {
    const selectedModes = ["walking", "modelled_vehicle"].filter((mode) => selectedPairs.has(`${service.id}/${mode}`));
    if (!selectedModes.length) continue;
    await serviceSelect.selectOption(service.id);
    for (const mode of selectedModes) {
      await modeSelect.selectOption(mode);
      const variant = service.variants.find((item) => item.travel_mode === mode && item.speed_factor === 1);
      const populationDialog = await openFinalsDetail(brief, "population");
      const flood = service.id === "hospital" ? analysis.flood_scenarios?.[mode] : null;
      const floodHeading = populationDialog.getByRole("heading", { name: th ? "ผลประชากรจากขอบเขตน้ำท่วมผู้สมัคร" : "Population consequences of the flood candidate", exact: true });
      if (flood) {
        await floodHeading.waitFor();
        const text = await populationDialog.innerText();
        if (!text.includes(flood.candidate_affected_population.toLocaleString(th ? "th-TH" : "en-GB", { maximumFractionDigits: 1 }))) throw new Error("Candidate-overlap population differs from package");
        if (!text.includes(th ? "Class E" : "Class E follows the low-confidence rule")) throw new Error("Candidate score confidence boundary lost");
      } else if (await floodHeading.count()) throw new Error("Hospital flood population substituted for another service");
      if (variant) {
        const displayed = await populationDialog.getByText(th ? "ประชากรตามแบบจำลองในขอบเขต" : "Modelled residents in scope", { exact: true }).locator("..").locator("strong").innerText();
        const expected = variant.baseline.modelled_population.toLocaleString(th ? "th-TH" : "en-GB", { maximumFractionDigits: 0 });
        if (displayed !== expected) throw new Error(`Service population differs: ${service.id}/${mode}, ${displayed} != ${expected}`);
      } else {
        await populationDialog.getByRole("status").filter({ hasText: th ? "ไม่มีผลสำหรับบริการที่เลือก" : "No result is available for this service" }).waitFor();
      }
      await closeFinalsDetail(page, brief, "population");
      if (!routes || routes.status !== "available") continue;
      const routePanel = brief.locator("[data-route-comparison]");
      for (const target of routeTargets.filter((item) => item.service === service.id && item.mode === mode)) {
        const pin = routes.origins.find((item) => item.id === target.originId);
        if (!pin) throw new Error(`Browser route matrix names an unknown origin: ${target.originId}`);
        await routePanel.getByRole("combobox", { name: th ? "จุดเริ่มต้นสาธารณะ" : "Public starting place", exact: true }).selectOption(pin.id);
        const kind = target.kind;
          await routePanel.getByRole("combobox", { name: th ? "การเปลี่ยนแปลงที่กำหนด" : "Imposed change", exact: true }).selectOption(kind);
          const expected = routes.comparisons.find((item) => item.origin_id === pin.id && item.service_type === service.id && item.travel_mode === mode && item.scenario_kind === kind);
          if (!expected) {
            await routePanel.getByText(th ? "ไม่มีผลเส้นทางสำหรับตัวเลือกนี้ จะไม่ใช้จุดเริ่มต้นหรือบริการอื่นแทน" : "No route comparison exists for this selection. Another origin or service is not substituted.", { exact: true }).waitFor();
            continue;
          }
          await page.waitForFunction((id) => document.querySelector("[data-route-comparison]")?.getAttribute("data-route-id") === id, expected.id);
          const populationHeadline = routePanel.locator("[data-flood-headline]");
          if (flood && kind === "close_edge") {
            await populationHeadline.waitFor();
            if (!(await populationHeadline.innerText()).includes(flood.impact.losing_30_min_access.toLocaleString(th ? "th-TH" : "en-GB", { maximumFractionDigits: 0 }))) throw new Error("Headline differs from selected population scenario");
          } else if (await populationHeadline.count()) throw new Error("Flood headline shown for a different intervention or service");
          await routePanel.locator(".leaflet-container canvas").first().waitFor({ state: "visible" });
          const selectedOrigin = routePanel.getByRole("combobox", { name: th ? "จุดเริ่มต้นสาธารณะ" : "Public starting place", exact: true });
          if (await selectedOrigin.inputValue() !== pin.id) throw new Error("Starting-place selector differs from route origin");
          const startTooltip = routePanel.locator(".leaflet-tooltip").filter({ has: page.locator("[data-route-start-label]") });
          await startTooltip.waitFor({ state: "visible" });
          const mapBox = await routePanel.locator(".leaflet-container").boundingBox();
          const startBox = await startTooltip.boundingBox();
          if (!mapBox || !startBox || startBox.x < mapBox.x || startBox.y < mapBox.y || startBox.x + startBox.width > mapBox.x + mapBox.width || startBox.y + startBox.height > mapBox.y + mapBox.height) throw new Error(`Starting-place tooltip is clipped: ${expected.id}, Thai=${th}`);
          await assertAvailabilityDoesNotOverlap(page, routePanel, expected.id);
          for (const phase of ["baseline", "after"]) {
            const result = expected[phase];
            const panel = routePanel.locator(`[data-route-result="${phase}"]`);
            await panel.waitFor();
            if (result.status === "available") {
              const time = result.total_minutes.toLocaleString(th ? "th-TH" : "en-GB", { maximumFractionDigits: 1 });
              const distance = (result.distance_m / 1000).toLocaleString(th ? "th-TH" : "en-GB", { maximumFractionDigits: 2 });
              if (await panel.locator("[data-route-total-minutes]").innerText() !== time || await panel.locator("[data-route-distance-km]").innerText() !== distance) throw new Error(`Route time/distance differs: ${expected.id}/${phase}`);
              await panel.getByRole("heading", { name: result.destination_name, exact: true }).waitFor();
            } else {
              if (await panel.locator("[data-route-total-minutes]").count()) throw new Error(`Unavailable route has numerical time: ${expected.id}/${phase}`);
              await routePanel.getByRole("button", { name: th ? "รายละเอียดเส้นทาง" : "Route details", exact: true }).click();
              const detail = routePanel.getByRole("dialog");
              await detail.waitFor({ state: "visible" });
              if (!(await detail.locator(`[data-route-detail-result="${phase}"]`).innerText()).includes(result.reason)) throw new Error(`Unavailable route reason lost: ${expected.id}/${phase}`);
              await page.keyboard.press("Escape");
              await detail.waitFor({ state: "hidden" });
            }
          }
          const status = await routePanel.getByRole("status").innerText();
          if (expected.delta_minutes === null) {
            if (!status.includes(th ? "ผลต่างเวลาไม่มี" : "Time difference unavailable") || !status.includes(th ? "ไม่ใช่ศูนย์" : "Missing time is not zero")) throw new Error(`Missing route became zero delay: ${expected.id}`);
          } else if (expected.delta_minutes === 0 && !status.includes(th ? "ไม่ต่างในกรณีนี้" : "No difference")) throw new Error(`Zero route effect hidden: ${expected.id}`);
          for (const [en, thai] of [["Before", "ก่อน"], ["After", "หลัง"], ["Both", "ทั้งสองกรณี"]]) {
            const radio = routePanel.getByRole("radio", { name: th ? thai : en, exact: true });
            await radio.check();
            if (!await radio.isChecked()) throw new Error(`Route overlay toggle failed: ${expected.id}/${en}`);
          }
          if (await brief.getByRole("alert").count()) throw new Error(`Finals route alert: ${expected.id}, offline=${offline}`);
          if (await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)) throw new Error(`Finals route viewport overflow: ${expected.id}, Thai=${th}, offline=${offline}`);
          routeCasesChecked += 1;
          routeCoverageCounts[target.category] += 1;
      }
    }
  }
  await serviceSelect.selectOption(analysis.primary_service);
  await modeSelect.selectOption("walking");
  if (routes?.origins.length) {
    const routePanel = brief.locator("[data-route-comparison]");
    await routePanel.getByRole("combobox", { name: th ? "จุดเริ่มต้นสาธารณะ" : "Public starting place", exact: true }).selectOption(routes.origins[0].id);
    await routePanel.getByRole("combobox", { name: th ? "การเปลี่ยนแปลงที่กำหนด" : "Imposed change", exact: true }).selectOption("close_edge");
  }
}

async function openFinalsDetail(brief, kind) {
  await brief.locator(`[data-finals-detail="${kind}"]`).click();
  const dialog = brief.getByRole("dialog");
  await dialog.waitFor({ state: "visible" });
  if (!await dialog.getAttribute("aria-labelledby") && !await dialog.getAttribute("aria-label")) throw new Error(`Finals ${kind} dialog has no accessible name.`);
  return dialog;
}

async function closeFinalsDetail(page, brief, kind) {
  await page.keyboard.press("Escape");
  await brief.getByRole("dialog").waitFor({ state: "hidden" });
  if (!await brief.locator(`[data-finals-detail="${kind}"]`).evaluate((button) => document.activeElement === button)) throw new Error(`Closing ${kind} does not restore focus to its trigger.`);
}

async function assertAvailabilityDoesNotOverlap(page, routePanel, identity) {
  const availability = page.locator("[data-pwa-availability]");
  if (!await availability.count() || !await availability.isVisible()) return;
  const badge = await availability.boundingBox();
  if (!badge) return;
  const critical = routePanel.locator('select, input, button, [data-route-result], [data-route-outcome], .leaflet-control-zoom');
  for (const item of await critical.all()) {
    if (!await item.isVisible()) continue;
    const box = await item.boundingBox();
    if (box && Math.min(badge.x + badge.width, box.x + box.width) > Math.max(badge.x, box.x) && Math.min(badge.y + badge.height, box.y + box.height) > Math.max(badge.y, box.y)) throw new Error(`Availability control covers route content: ${identity}`);
  }
}

async function assertFitsViewport(page, locator, label, interactive = false) {
  await locator.waitFor({ state: "visible" });
  const bounds = await locator.boundingBox();
  const viewport = page.viewportSize();
  if (!bounds || bounds.width < 1 || bounds.height < 1 || bounds.x < -1 || bounds.y < -1 || bounds.x + bounds.width > viewport.width + 1 || bounds.y + bounds.height > viewport.height + 1) throw new Error(`Workspace ${label} is outside ${viewport.width}×${viewport.height}: ${JSON.stringify(bounds)}`);
  if (interactive && !await locator.evaluate((element) => {
    const box = element.getBoundingClientRect();
    const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
    return hit === element || element.contains(hit);
  })) {
    if (captureDirectory) await page.screenshot({ path: resolve(captureDirectory, "workspace-overlap.png") });
    const covering = await locator.evaluate((element) => {
      const box = element.getBoundingClientRect();
      const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
      return { expected: element.textContent, actual: hit?.outerHTML.slice(0, 400) };
    });
    throw new Error(`Workspace ${label} is covered at ${viewport.width}×${viewport.height}: ${JSON.stringify(covering)}`);
  }
}

async function verifyRouteWorkspace(page, aoiId = "aoi-01_mae_sai_core") {
  const reference = catalog.packages.find((item) => item.aoi_id === aoiId);
  if (!reference) throw new Error(`Route-workspace package is missing: ${aoiId}`);
  await page.goto(`${origin}/studio/brief/?aoi=${reference.aoi_id}&event=${reference.event_id}`, { waitUntil: "networkidle" });
  const brief = page.locator("[data-decision-brief]");
  const routePanel = brief.locator("[data-route-comparison]");
  for (const viewport of [{ width: 1366, height: 768 }, { width: 1024, height: 768 }, { width: 390, height: 844 }, { width: 375, height: 667 }]) {
    await page.setViewportSize(viewport);
    const mobileDocument = viewport.width <= 700;
    const checkWorkspaceItem = async (locator, label, interactive = false) => {
      if (mobileDocument) await locator.scrollIntoViewIfNeeded();
      await assertFitsViewport(page, locator, label, interactive);
    };
    for (const th of [false, true]) {
      const toggle = page.getByRole("button", { name: th ? "ใช้ภาษาไทย" : "Use English", exact: true });
      if (await toggle.count()) await toggle.click();
      await routePanel.locator(".leaflet-container canvas").first().waitFor({ state: "visible" });
      await page.evaluate(() => window.scrollTo(0, 0));
      await checkWorkspaceItem(page.locator("#evidence-case"), "study area and event selector", true);
      for (const label of th ? ["บริการที่ต้องการ", "วิธีเดินทางตามแบบจำลอง", "จุดเริ่มต้นสาธารณะ", "การเปลี่ยนแปลงที่กำหนด"] : ["Service needed", "Modelled travel mode", "Public starting place", "Imposed change"]) {
        await checkWorkspaceItem(brief.getByRole("combobox", { name: label, exact: true }), label, true);
      }
      for (const radio of await routePanel.getByRole("radio").all()) await checkWorkspaceItem(radio, "route overlay selector", true);
      for (const kind of ["population", "interventions", "evidence"]) await checkWorkspaceItem(brief.locator(`[data-finals-detail="${kind}"]`), `${kind} detail button`, true);
      await checkWorkspaceItem(routePanel.locator(".leaflet-container"), "route map");
      await checkWorkspaceItem(routePanel.locator('[data-route-result="baseline"]'), "before result");
      await checkWorkspaceItem(routePanel.locator('[data-route-result="after"]'), "after result");
      await checkWorkspaceItem(routePanel.locator("[data-route-outcome]"), "route change result");
      await checkWorkspaceItem(routePanel.locator("[data-route-caution]"), "route uncertainty");
      for (const item of await routePanel.getByRole("list", { name: th ? "สัญลักษณ์เส้นทาง" : "Route legend", exact: true }).getByRole("listitem").all()) await checkWorkspaceItem(item, "route legend item", true);
      const dimensions = await page.evaluate(() => ({ width: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight, viewportWidth: innerWidth, viewportHeight: innerHeight }));
      if (dimensions.width > dimensions.viewportWidth + 1 || (!mobileDocument && dimensions.height > dimensions.viewportHeight + 1)) throw new Error(`Route workspace overflows at ${viewport.width}×${viewport.height}, Thai=${th}: ${JSON.stringify(dimensions)}`);
      if (mobileDocument) {
        const resultTop = await routePanel.locator('[data-route-result="baseline"]').evaluate((element) => element.getBoundingClientRect().top + scrollY);
        const mapTop = await routePanel.locator(".leaflet-container").evaluate((element) => element.getBoundingClientRect().top + scrollY);
        if (resultTop >= mapTop) throw new Error(`Phone route result must appear before the map: ${viewport.width}×${viewport.height}`);
      }
      await assertAvailabilityDoesNotOverlap(page, routePanel, `${viewport.width}×${viewport.height}, Thai=${th}`);
      if (captureDirectory) await page.screenshot({ path: resolve(captureDirectory, `${aoiId}-route-workspace-${viewport.width}x${viewport.height}-${th ? "th" : "en"}.png`) });
      for (const [en, thai, green, purple] of (aoiId === "aoi-01_mae_sai_core" ? [["Before", "ก่อน", true, false], ["After", "หลัง", false, true], ["Both", "ทั้งสองกรณี", true, true]] : [])) {
        await routePanel.getByRole("radio", { name: th ? thai : en, exact: true }).check();
        await page.waitForFunction(({ green, purple }) => {
          let greenPixels = 0;
          let purplePixels = 0;
          for (const canvas of document.querySelectorAll("[data-route-comparison] .leaflet-container canvas")) {
            const context = canvas.getContext("2d");
            if (!context) continue;
            const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
            for (let index = 0; index < pixels.length; index += 4) {
              const red = pixels[index], g = pixels[index + 1], blue = pixels[index + 2], alpha = pixels[index + 3];
              if (alpha < 100) continue;
              if (red < 90 && g > 100 && g > blue && g - red > 40) greenPixels += 1;
              if (red > 100 && red < 190 && g < 130 && blue > 140 && blue - red > 20 && red - g > 30) purplePixels += 1;
            }
          }
          return (green ? greenPixels > 5 : greenPixels === 0) && (purple ? purplePixels > 5 : purplePixels === 0);
        }, { green, purple }, { timeout: 5000 });
      }

      const routeId = await routePanel.getAttribute("data-route-id");
      for (const kind of ["population", "interventions", "evidence"]) {
        const dialog = await openFinalsDetail(brief, kind);
        await checkWorkspaceItem(dialog, `${kind} dialog`);
        await page.keyboard.press("Tab");
        if (!await dialog.evaluate((element) => element.contains(document.activeElement))) throw new Error(`Keyboard focus escaped the ${kind} modal.`);
        if (kind === "population") {
          await dialog.locator('[data-detail-tab="population"]').focus();
          for (const [key, expectedTab] of [["End", "evidence"], ["Home", "population"], ["ArrowRight", "interventions"], ["ArrowLeft", "population"]]) {
            await page.keyboard.press(key);
            if (await dialog.locator(`[data-detail-tab="${expectedTab}"]`).getAttribute("aria-selected") !== "true") throw new Error(`Detail tab keyboard navigation failed: ${key}`);
          }
        }
        await closeFinalsDetail(page, brief, kind);
        if (await routePanel.getAttribute("data-route-id") !== routeId) throw new Error(`Opening ${kind} reset the selected route.`);
      }
      const detailsButton = routePanel.getByRole("button", { name: th ? "รายละเอียดเส้นทาง" : "Route details", exact: true });
      await checkWorkspaceItem(detailsButton, "route details button", true);
      await detailsButton.click();
      const routeDialog = page.getByRole("dialog");
      await routeDialog.waitFor({ state: "visible" });
      await routeDialog.getByText(th ? "แหล่งข้อมูลจุดเริ่มต้น" : "Starting-place source", { exact: true }).waitFor();
      await page.keyboard.press("Escape");
      await routeDialog.waitFor({ state: "hidden" });
      if (!await detailsButton.evaluate((button) => document.activeElement === button)) throw new Error("Route details dialog did not restore trigger focus.");

      const sourcesButton = page.getByRole("button", { name: th ? "แหล่งข้อมูลและดาวน์โหลด" : "Sources and downloads", exact: true });
      await checkWorkspaceItem(sourcesButton, "sources and downloads button", true);
      await sourcesButton.click();
      const sourcesDialog = page.getByRole("dialog");
      await sourcesDialog.waitFor({ state: "visible" });
      await sourcesDialog.getByRole("link", { name: th ? "ดาวน์โหลดรายงาน" : "Download report", exact: true }).waitFor();
      if (!(await sourcesDialog.innerText()).includes(reference.id)) throw new Error("Sources dialog lost the selected package identity.");
      await sourcesDialog.getByRole("button", { name: th ? "ปิด" : "Close", exact: true }).click();
      await sourcesDialog.waitFor({ state: "hidden" });
      if (!await sourcesButton.evaluate((button) => document.activeElement === button)) throw new Error("Sources dialog did not restore trigger focus after clicking Close.");
      workspaceViewportsChecked += 1;
    }
  }
  const englishToggle = page.getByRole("button", { name: "Use English", exact: true });
  if (await englishToggle.count()) await englishToggle.click();
  await page.setViewportSize({ width: 320, height: 360 });
  for (const control of await page.locator('main[data-route-workspace="true"] select').all()) {
    await control.scrollIntoViewIfNeeded();
    await assertFitsViewport(page, control, "reflowed selector", true);
  }
  for (const phase of ["baseline", "after"]) {
    const result = routePanel.locator(`[data-route-result="${phase}"]`);
    await result.scrollIntoViewIfNeeded();
    await assertFitsViewport(page, result, `reflowed ${phase} result`);
  }
  const dialog = await openFinalsDetail(brief, "evidence");
  await assertFitsViewport(page, dialog.getByRole("button", { name: "Close", exact: true }), "reflowed dialog close button", true);
  await closeFinalsDetail(page, brief, "evidence");
  if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)) throw new Error("Route workspace has horizontal overflow at the small reflow viewport.");
}
