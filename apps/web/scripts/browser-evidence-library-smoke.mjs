import { createReadStream, existsSync, readFileSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, resolve, sep } from "node:path";
import { launchFloodGuardBrowser } from "./browser-launch.mjs";

const out = resolve(process.env.FLOODGUARD_PROFILE_OUT ?? resolve(process.cwd(), "out"));
const catalog = JSON.parse(readFileSync(resolve(out, "evidence-library", "catalog.json"), "utf8"));
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
let routeCasesChecked = 0;
const browser = await launchFloodGuardBrowser();
try {
  const context = await browser.newContext({ serviceWorkers: "allow", viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const errors = [];
  const invalidRequests = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => { const url = new URL(request.url()); if (url.origin !== origin || url.pathname.startsWith("/api/")) invalidRequests.push(url.href); });
  await page.goto(`${origin}/studio/library/`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "Study-area evidence library" }).waitFor();
  await page.waitForFunction(() => Boolean(navigator.serviceWorker.controller));
  for (const reference of catalog.packages) {
    await page.selectOption("#evidence-aoi", reference.aoi_id);
    await page.selectOption("#evidence-event", reference.event_id);
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
    await page.selectOption("#evidence-aoi", item.aoi_id);
    await page.selectOption("#evidence-event", item.event_id);
    await page.locator("main[data-evidence-library] footer").filter({ hasText: item.id }).waitFor();
  }
  await verifyDecisionBrief(page, true);
  await page.setViewportSize({ width: 390, height: 844 });
  if (await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)) throw new Error("Evidence library overflows the mobile viewport.");
  if (errors.length) throw new Error(`Browser errors: ${errors.join("; ")}`);
  if (invalidRequests.length) throw new Error(`Unexpected browser requests: ${invalidRequests.join("; ")}`);
  console.log(`Evidence library and decision brief browser: ${catalog.packages.length} AOI/event packages online and offline; ${routeCasesChecked} exact route comparisons across service, mode, origin, change, Thai/English and desktop/mobile; exact population and intervention counts, invalid selections, report download and no API requests passed.`);
  await context.close();
} finally {
  await browser.close();
  await new Promise((done) => server.close(done));
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
      await page.getByRole("heading", { name: th ? "บทสรุปเพื่อการตัดสินใจ" : "Study-area decision brief", exact: true }).waitFor();
      for (const reference of catalog.packages) {
        await page.selectOption("#evidence-aoi", reference.aoi_id);
        await page.selectOption("#evidence-event", reference.event_id);
        await main.locator("footer").filter({ hasText: reference.id }).waitFor();
        const evidence = JSON.parse(readFileSync(resolve(out, reference.url.replace(/^\//, "")), "utf8"));
        if (!evidence.decision_brief) throw new Error(`Decision brief package missing: ${reference.id}`);
        const brief = main.locator("[data-decision-brief]");
        await brief.waitFor();
        if (await main.getByRole("alert").count()) throw new Error(`Decision brief has an alert: ${reference.id}`);
        if (evidence.decision_brief.finals_analysis) {
          await verifyFinalsComparison(page, brief, evidence.decision_brief.finals_analysis, th, offline);
        } else if (evidence.decision_brief.access) {
          if (await brief.locator("[data-brief-intervention]").count() !== evidence.decision_brief.interventions.length) throw new Error(`Decision brief intervention count differs from selected package: ${reference.id}`);
          const label = th ? "ประชากรตามแบบจำลองในพื้นที่ศึกษา (ปี 2020)" : "Modelled residents in the study area (2020)";
          const displayed = await brief.getByText(label, { exact: true }).locator("..").locator("dd").innerText();
          const expected = evidence.decision_brief.access.modelled_population.toLocaleString(th ? "th-TH" : "en-GB", { maximumFractionDigits: 1 });
          if (displayed !== expected) throw new Error(`Decision brief population differs from selected package: ${reference.id}: ${displayed} != ${expected}`);
        } else {
          await brief.getByText(th ? "พื้นที่นี้มีข้อมูลความครอบคลุม ยังไม่มีการคำนวณการเข้าถึง" : "This area has an evidence-coverage view; access calculations are unavailable.", { exact: true }).waitFor();
        }
        const text = await brief.innerText();
        for (const boundary of th ? ["คะแนน / ระดับการดำเนินการ", "ยังไม่พร้อม", "ประชากรที่ได้รับผลจากน้ำท่วม", "ยังไม่ทราบ"] : ["FPPS / action class", "Unavailable", "Flood-affected population", "Unknown"]) {
          if (!text.includes(boundary)) throw new Error(`Decision brief lost its unknown-evidence boundary: ${reference.id}: ${boundary}`);
        }
        if (await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)) throw new Error(`Decision brief overflows ${viewport.width}px: ${reference.id}, Thai=${th}, offline=${offline}`);
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

async function verifyFinalsComparison(page, brief, analysis, th, offline) {
  await brief.locator("[data-finals-analysis]").waitFor();
  const serviceSelect = brief.getByRole("combobox", { name: th ? "บริการที่ต้องการ" : "Service needed", exact: true });
  const modeSelect = brief.getByRole("combobox", { name: th ? "วิธีเดินทางตามแบบจำลอง" : "Modelled travel mode", exact: true });
  const routes = analysis.routes;
  for (const service of analysis.services) {
    await serviceSelect.selectOption(service.id);
    for (const mode of ["walking", "modelled_vehicle"]) {
      await modeSelect.selectOption(mode);
      const variant = service.variants.find((item) => item.travel_mode === mode && item.speed_factor === 1);
      if (variant) {
        const displayed = await brief.getByText(th ? "ประชากรตามแบบจำลองในขอบเขต" : "Modelled residents in scope", { exact: true }).locator("..").locator("strong").innerText();
        const expected = variant.baseline.modelled_population.toLocaleString(th ? "th-TH" : "en-GB", { maximumFractionDigits: 0 });
        if (displayed !== expected) throw new Error(`Service population differs: ${service.id}/${mode}, ${displayed} != ${expected}`);
      } else {
        await brief.getByRole("status").filter({ hasText: th ? "ไม่มีผลสำหรับบริการที่เลือก" : "No result is available for this service" }).waitFor();
      }
      if (!routes || routes.status !== "available") continue;
      const routePanel = brief.locator("[data-route-comparison]");
      for (const pin of routes.origins) {
        await routePanel.getByRole("combobox", { name: th ? "จุดเริ่มต้นสาธารณะ" : "Public starting place", exact: true }).selectOption(pin.id);
        for (const kind of ["close_edge", "remove_destination"]) {
          await routePanel.getByRole("combobox", { name: th ? "การเปลี่ยนแปลงที่กำหนด" : "Imposed change", exact: true }).selectOption(kind);
          const expected = routes.comparisons.find((item) => item.origin_id === pin.id && item.service_type === service.id && item.travel_mode === mode && item.scenario_kind === kind);
          if (!expected) {
            await routePanel.getByText(th ? "ไม่มีผลเส้นทางสำหรับตัวเลือกนี้ จะไม่ใช้จุดเริ่มต้นหรือบริการอื่นแทน" : "No route comparison exists for this selection. Another origin or service is not substituted.", { exact: true }).waitFor();
            continue;
          }
          await page.waitForFunction((id) => document.querySelector("[data-route-comparison]")?.getAttribute("data-route-id") === id, expected.id);
          await routePanel.locator(".leaflet-container canvas").first().waitFor({ state: "visible" });
          await routePanel.locator("[data-route-origin]").filter({ hasText: pin.name }).waitFor();
          const startTooltip = routePanel.locator(".leaflet-tooltip").filter({ has: page.locator("[data-route-start-label]") });
          await startTooltip.waitFor({ state: "visible" });
          const mapBox = await routePanel.locator(".leaflet-container").boundingBox();
          const startBox = await startTooltip.boundingBox();
          if (!mapBox || !startBox || startBox.x < mapBox.x || startBox.y < mapBox.y || startBox.x + startBox.width > mapBox.x + mapBox.width || startBox.y + startBox.height > mapBox.y + mapBox.height) throw new Error(`Starting-place tooltip is clipped: ${expected.id}, Thai=${th}`);
          if (page.viewportSize().width <= 560) {
            const availability = page.locator("[data-pwa-availability]");
            if (await availability.count()) {
              const badgeBox = await availability.boundingBox();
              const reportBox = await page.locator("main[data-evidence-library]").boundingBox();
              if (badgeBox && reportBox && badgeBox.y < reportBox.y + reportBox.height) throw new Error(`Availability control overlaps the mobile evidence report: ${expected.id}`);
            }
          }
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
              if (!(await panel.innerText()).includes(result.reason)) throw new Error(`Unavailable route reason lost: ${expected.id}/${phase}`);
            }
          }
          const status = await routePanel.getByRole("status").innerText();
          if (expected.delta_minutes === null) {
            if (!status.includes(th ? "ไม่มีผลต่างเวลา" : "a time difference is unavailable")) throw new Error(`Missing route became zero delay: ${expected.id}`);
          } else if (expected.delta_minutes === 0 && !status.includes(th ? "ไม่พบความต่าง" : "No difference")) throw new Error(`Zero route effect hidden: ${expected.id}`);
          for (const [en, thai] of [["Before", "ก่อน"], ["After", "หลัง"], ["Both", "ทั้งสองกรณี"]]) {
            const radio = routePanel.getByRole("radio", { name: th ? thai : en, exact: true });
            await radio.check();
            if (!await radio.isChecked()) throw new Error(`Route overlay toggle failed: ${expected.id}/${en}`);
          }
          if (await brief.getByRole("alert").count()) throw new Error(`Finals route alert: ${expected.id}, offline=${offline}`);
          if (await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)) throw new Error(`Finals route viewport overflow: ${expected.id}, Thai=${th}, offline=${offline}`);
          routeCasesChecked += 1;
        }
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
