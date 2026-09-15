import assert from "node:assert/strict";
import { createReadStream, existsSync, mkdirSync, statSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { extname, resolve, sep } from "node:path";
import { expect } from "@playwright/test";
import { launchFloodGuardBrowser } from "./browser-launch.mjs";

const output = resolve(process.env.FLOODGUARD_PROFILE_OUT ?? "out");
const artifacts = resolve("test-results/studio-studies");
mkdirSync(artifacts, { recursive: true });
let server;
let baseUrl = process.env.FLOODGUARD_STUDY_BASE_URL;
if (!baseUrl) {
  assert(existsSync(resolve(output, "studio/studies/c2s-ms-20260915/index.html")), "Build the static study routes before running this check.");
  const types = { ".html":"text/html", ".js":"text/javascript", ".css":"text/css", ".json":"application/json", ".png":"image/png", ".svg":"image/svg+xml", ".woff2":"font/woff2" };
  server = createServer((request, response) => {
    const path = decodeURIComponent(new URL(request.url ?? "/", "http://localhost").pathname).replace(/^\/+/, "");
    let file = resolve(output, path || "index.html");
    if (file !== output && !file.startsWith(`${output}${sep}`)) return response.writeHead(403).end();
    if (existsSync(file) && statSync(file).isDirectory()) file = resolve(file, "index.html");
    if (!existsSync(file) || !statSync(file).isFile()) return response.writeHead(404).end("Unavailable");
    response.writeHead(200, { "Content-Type": types[extname(file)] ?? "application/octet-stream", "Cache-Control":"no-store" });
    createReadStream(file).pipe(response);
  });
  await new Promise((done) => server.listen(0, "127.0.0.1", done));
  baseUrl = `http://127.0.0.1:${server.address().port}`;
}

const study = "/studio/studies/c2s-ms-20260915/";
const browser = await launchFloodGuardBrowser();
const checks = [];
try {
  const context = await browser.newContext({ viewport:{width:1440,height:1000}, serviceWorkers:"block" });
  await context.route("**/*", (route) => new URL(route.request().url()).origin === new URL(baseUrl).origin ? route.continue() : route.abort());
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  async function visit(path, ready) {
    const response = await page.goto(`${baseUrl}${path}`, { waitUntil:"networkidle" });
    assert.equal(response?.status(), 200, `Direct route ${path}`);
    await expect(page.getByText(ready, {exact:false}).first()).toBeVisible();
    assert.equal(await page.getByRole("alert").count(), 0, `No evidence errors at ${path}`);
    checks.push(`direct route ${path}`);
  }
  await visit(study, "What the experiment establishes");
  await visit(`${study}data/`, "Five separate jobs for the data");
  await expect(page.locator("svg path").first()).toBeVisible();
  await page.getByLabel("Show event role").selectOption("test");
  await expect(page).toHaveURL(/role=test/);
  await expect(page.locator("tr[id^=event-]")).toHaveCount(3);
  await page.reload({waitUntil:"networkidle"});
  await expect(page.getByLabel("Show event role")).toHaveValue("test");
  checks.push("event filter survives reload");
  await visit(`${study}models/`, "XGBoost · recorded fit");
  await expect(page.getByText("XGBoost feature contributions", {exact:true})).toBeVisible();
  await page.getByLabel("Model and input version").selectOption("sar/unet");
  await expect(page.getByText("U-Net · recorded fit", {exact:true})).toBeVisible();
  await visit(`${study}results/`, "10,455,894");
  await page.getByLabel("Probability version").selectOption("raw");
  await expect(page).toHaveURL(/calibration=raw/);
  await expect(page.getByText("0.7735", {exact:true}).first()).toBeVisible();
  await page.goBack({waitUntil:"networkidle"});
  await expect(page.getByLabel("Probability version")).toHaveValue("calibrated");
  await page.getByLabel("Comparison view").selectOption("events");
  await expect(page.getByText("Nigeria", {exact:true}).first()).toBeVisible();
  checks.push("raw/calibrated and event results shareable; browser Back restores state");
  await visit(`${study}rtc/`, "The fixed 1–5 dB change ramp");
  await expect(page.getByText("11,732,437", {exact:true}).first()).toBeVisible();
  await visit(`${study}explorer/`, "Human water reference");
  await expect(page.getByText("0.1334", {exact:true})).toBeVisible();
  const initialChip = await page.getByLabel(/^Chip \(/).inputValue();
  await page.getByLabel("Model", {exact:true}).selectOption("xgboost");
  await page.getByLabel("Input version", {exact:true}).selectOption("sar");
  await expect(page.getByRole("img", {name:"Prediction errors against the human reference"})).toBeVisible();
  await page.reload({waitUntil:"networkidle"});
  await expect(page.getByLabel("Input version", {exact:true})).toHaveValue("sar");
  await expect(page.getByLabel("Model", {exact:true})).toHaveValue("xgboost");
  const index = await (await context.request.get(`${baseUrl}/studies/c2s-ms-20260915/r1/visual-index.json`)).json();
  const missing = index.chips.find((chip) => chip.models.context.unet.status === "unavailable");
  assert(missing, "An unsupported context chip stays in the visual catalogue.");
  await page.goto(`${baseUrl}${study}explorer/?arm=context&model=unet&chip=${encodeURIComponent(missing.chip_id)}`, {waitUntil:"networkidle"});
  await expect(page.getByRole("alert")).toContainText("Model preview unavailable");
  assert.equal(await page.getByRole("img",{name:"Binary water prediction"}).count(),0);
  checks.push("Australian U-Net failure visible and unsupported context case fails closed");
  await visit(`${study}files/`, "Reproduce the recorded result");
  for (const link of await page.locator("a[download]").evaluateAll((nodes) => nodes.map((node) => node.href))) {
    assert.equal((await context.request.get(link)).status(),200,`Download ${link}`);
  }
  checks.push("all presented study downloads resolve");
  await visit(`${study}mae-sai/`, "Inference identity and model lineage");
  for (const arm of ["sar","context"]) for (const model of ["random_forest","xgboost","unet"]) {
    await page.getByLabel("Input version", {exact:true}).selectOption(arm);
    await page.getByLabel("Model", {exact:true}).selectOption(model);
    for (const layer of ["probability","validity","entropy","abstention"]) {
      await page.getByLabel("Map layer").selectOption(layer);
      await page.waitForFunction(() => [...document.querySelectorAll("figure img")].every((img) => img.complete && img.naturalWidth > 0));
      assert.equal(await page.getByRole("alert").count(),0,`Mae Sai ${arm}/${model}/${layer}`);
    }
  }
  const maeText = await page.locator("main").innerText();
  assert(!/\bIoU\b|0\.8661|Human water reference/.test(maeText), "Mae Sai cannot show benchmark scores or a local human reference.");
  checks.push("all 24 Mae Sai model/input/layer combinations render without local accuracy claims");
  await page.screenshot({path:resolve(artifacts,"mae-sai-desktop.png"),fullPage:true});
  await visit("/studio/archive/mae-sai-geoai/", "Historical research");
  await expect(page.getByText(/teacher agreement|Teacher agreement|distillation fidelity/).first()).toBeVisible();
  await visit("/studio/", "Every result has a context.");
  await page.screenshot({path:resolve(artifacts,"studio-library-desktop.png"),fullPage:true});
  for (const path of [study, `${study}data/`, `${study}results/`, `${study}explorer/?chip=${encodeURIComponent(initialChip)}`, `${study}mae-sai/`]) {
    await page.setViewportSize({width:390,height:844});
    await page.goto(`${baseUrl}${path}`,{waitUntil:"networkidle"});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),`No page overflow at ${path}`);
    await expect(page.getByLabel("Study section",{exact:true})).toBeVisible();
  }
  await page.screenshot({path:resolve(artifacts,"mae-sai-mobile.png"),fullPage:true});
  checks.push("mobile layout and compact section navigation");
  const broken = await context.newPage();
  await broken.route("**/studies/c2s-ms-20260915/r1/summary.json",route=>route.fulfill({status:404,body:"missing"}));
  await broken.goto(`${baseUrl}${study}results/`,{waitUntil:"networkidle"});
  await expect(broken.getByRole("alert")).toContainText("Study asset unavailable");
  assert(!(await broken.locator("main").innerText()).includes("0.8661"));
  checks.push("missing report fails closed without historical or planning fallback");
  await broken.unrouteAll();
  await broken.goto(`${baseUrl}${study}results/?revision=r99`,{waitUntil:"networkidle"});
  await expect(broken.getByRole("alert")).toContainText("Study revision unavailable");
  checks.push("unknown revision cannot silently reuse r1");
  assert.deepEqual(pageErrors, [], "No client exceptions during study navigation.");
  writeFileSync(resolve(artifacts,"verification.json"),JSON.stringify({checked_at:new Date().toISOString(),base_url:baseUrl,status:"passed",checks},null,2));
  console.log(JSON.stringify({status:"passed",checks:checks.length,artifacts},null,2));
} finally {
  await browser.close();
  if(server) await new Promise((done)=>server.close(done));
}
