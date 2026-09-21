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
    if (await page.getByRole("alert").count()) throw new Error(`Evidence package has an alert: ${reference.id}`);
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
  await page.setViewportSize({ width: 390, height: 844 });
  if (await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)) throw new Error("Evidence library overflows the mobile viewport.");
  if (errors.length) throw new Error(`Browser errors: ${errors.join("; ")}`);
  if (invalidRequests.length) throw new Error(`Unexpected browser requests: ${invalidRequests.join("; ")}`);
  console.log(`Evidence library browser: ${catalog.packages.length} AOI/event packages online and offline; Thai/English, invalid selection, report download, mobile layout and no API requests passed.`);
  await context.close();
} finally {
  await browser.close();
  await new Promise((done) => server.close(done));
}
