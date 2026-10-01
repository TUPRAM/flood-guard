import assert from "node:assert/strict";
import { createReadStream, existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { extname, resolve, sep } from "node:path";
import { expect } from "@playwright/test";
import { launchFloodGuardBrowser } from "./browser-launch.mjs";

const output = resolve(process.env.FLOODGUARD_PROFILE_OUT ?? "out");
const artifacts = resolve("../../.tmp/policy-qa");
assert(existsSync(resolve(output, "policy/index.html")), "Build the competition profile before testing policy.");
assert.equal(JSON.parse(readFileSync(resolve(output, "deployment-profile.json"), "utf8")).profile, "competition");
mkdirSync(artifacts, { recursive: true });
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".png": "image/png", ".webp": "image/webp", ".svg": "image/svg+xml", ".woff2": "font/woff2" };
const server = createServer((request, response) => {
  const pathname = decodeURIComponent(new URL(request.url ?? "/", "http://localhost").pathname).replace(/^\/+/, "");
  let file = resolve(output, pathname || "index.html");
  if (file !== output && !file.startsWith(`${output}${sep}`)) return response.writeHead(403).end();
  if (existsSync(file) && statSync(file).isDirectory()) file = resolve(file, "index.html");
  if (!existsSync(file) || !statSync(file).isFile()) return response.writeHead(404).end("Unavailable");
  response.writeHead(200, { "Content-Type": types[extname(file)] ?? "application/octet-stream", "Cache-Control": "no-store", "Service-Worker-Allowed": "/" });
  createReadStream(file).pipe(response);
});
await new Promise((done, reject) => { server.once("error", reject); server.listen(0, "127.0.0.1", done); });
const baseUrl = `http://127.0.0.1:${server.address().port}`;
const errors = [];
const checks = [];
let browser;
const replayRoute = "/studio/cases/mae-sai-2024/";
/** The replay's study data. Only an offline visit before it was saved may fail to load it. */
const replayDataPath = "/studies/mae-sai-2024-timeline/";
const offlineLoadFailure = /^(?:Failed to load resource: )?net::(?:ERR_INTERNET_DISCONNECTED|ERR_FAILED)$/;
const isReplayData = (url) => { try { return new URL(url).pathname.startsWith(replayDataPath); } catch { return false; } };
/**
 * Page errors and console errors always count. `offlineReplayData()` is true only during the deliberate offline visit
 * to the replay before its data was saved; then a failed load of that data, and only that, is expected.
 */
const recordErrors = (page, offlineReplayData = () => false) => {
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() !== "error") return;
    if (offlineReplayData() && offlineLoadFailure.test(message.text()) && isReplayData(message.location().url)) return;
    errors.push(`${message.text()} ${message.location().url}`.trim());
  });
  page.on("requestfailed", (request) => {
    const failure = request.failure()?.errorText ?? "";
    if (failure === "net::ERR_ABORTED") return;
    if (offlineReplayData() && offlineLoadFailure.test(failure) && isReplayData(request.url())) return;
    errors.push(`${request.method()} ${request.url()} (${request.resourceType()}): ${failure}`);
  });
};
/**
 * Text that runs past its section (or, outside a section, the viewport), or past an ancestor that clips it with
 * `overflow: hidden`. `document.scrollWidth` alone misses both. Scroll containers (the chapter nav), visually hidden
 * text (clip-path) and transformed glyphs (the rotated "+" of an open disclosure, whose rotated box is not layout) are
 * skipped.
 */
const overflowingText = (page) => page.evaluate(() => {
  const main = document.querySelector("main");
  const hits = [];
  const walker = document.createTreeWalker(main, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (!node.textContent.trim()) continue;
    let left = 0;
    let right = innerWidth;
    let skip = false;
    for (let element = node.parentElement; element && element !== main.parentElement; element = element.parentElement) {
      const style = getComputedStyle(element);
      if (style.clipPath !== "none" || style.transform !== "none" || /auto|scroll/.test(style.overflowX)) { skip = true; break; }
      if (element.tagName === "SECTION" || /hidden|clip/.test(style.overflowX)) {
        const box = element.getBoundingClientRect();
        left = Math.max(left, box.left);
        right = Math.min(right, box.right);
      }
    }
    if (skip) continue;
    const range = document.createRange();
    range.selectNodeContents(node);
    const rect = range.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) continue;
    if (rect.left < left - 1 || rect.right > right + 1) {
      hits.push(`${node.parentElement.tagName.toLowerCase()} "${node.textContent.trim().slice(0, 40)}" spans ${Math.round(rect.left)}-${Math.round(rect.right)}px, its box ${Math.round(left)}-${Math.round(right)}px`);
    }
  }
  return hits;
});
const replayTitle = "Mae Sai flood, September 2024 — day by day";
const widths = [320, 390, 430, 704, 768, 820, 900, 1024, 1440, 2048];
const scores = ["89.34", "85.98", "81.14", "76.38", "66.13", "53.93", "34.09", "31.27"];
// The replay's street basemap is the one off-site layer; answer it locally so the check never needs the network.
const blankTile = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=", "base64");
const keepLocal = (context) => context.route("**/*", (route) => {
  const url = new URL(route.request().url());
  if (url.origin === new URL(baseUrl).origin) return route.continue();
  if (route.request().resourceType() === "image") return route.fulfill({ status: 200, contentType: "image/png", body: blankTile });
  return route.abort("aborted");
});
const roles = [
  ["Public", "ประชาชน", "What should my household prepare?", "ครัวเรือนควรเตรียมอะไร?", "/public/"],
  ["Planning", "การวางแผน", "Where should we focus, and why?", "ควรให้ความสำคัญกับพื้นที่ใด เพราะอะไร?", "/command/"],
  ["Studio", "สตูดิโอ", "Is the evidence fit for this decision?", "หลักฐานเหมาะกับการตัดสินใจนี้หรือไม่?", "/studio/"],
];
const actions = [
  ["A", "Protect lives now", "ปกป้องชีวิตทันที"], ["B", "Keep routes open", "รักษาเส้นทางให้สัญจรได้"],
  ["C", "Protect essential services", "คุ้มครองบริการจำเป็น"], ["D", "Build resilience", "สร้างความพร้อมระยะยาว"],
  ["E", "Monitor and verify", "ติดตามและตรวจสอบ"],
];

try {
  browser = await launchFloodGuardBrowser();
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, serviceWorkers: "block", reducedMotion: "reduce" });
  await keepLocal(context);
  const page = await context.newPage();
  recordErrors(page);
  assert.equal((await page.goto(`${baseUrl}/policy/`, { waitUntil: "networkidle" }))?.status(), 200);
  await expect(page.locator("h1")).toContainText("From flood evidence");
  await expect(page).toHaveTitle("Policy & public value · นโยบายและประโยชน์ต่อสังคม · FloodGuard Thailand");

  // Keyboard first, before any pointer use: a visible focus ring, and disclosures that open from the keyboard.
  // The layout skip link comes first; the next stop is the page header brand link.
  await page.keyboard.press("Tab");
  await page.keyboard.press("Tab");
  const ring = await page.evaluate(() => {
    const style = getComputedStyle(document.activeElement);
    return { tag: document.activeElement.tagName, inMain: Boolean(document.activeElement.closest("main")), outline: style.outlineStyle, width: parseFloat(style.outlineWidth) };
  });
  assert(ring.tag === "A" && ring.inMain && ring.outline !== "none" && ring.width >= 2, `Keyboard focus is visible: ${JSON.stringify(ring)}`);
  const firstRules = page.locator("#priorities details").first();
  await firstRules.locator("summary").focus();
  await page.keyboard.press("Enter");
  await expect(firstRules).toHaveAttribute("open", "");
  await page.keyboard.press("Enter");
  await expect(firstRules).not.toHaveAttribute("open", "");
  const headings = await page.evaluate(() => [...document.querySelectorAll("main :is(h1,h2,h3,h4,h5,h6)")].map((node) => Number(node.tagName[1])));
  headings.forEach((level, index) => assert(index === 0 || level - headings[index - 1] <= 1, `Heading order jumps to h${level} at ${index}`));
  checks.push("visible keyboard focus, keyboard-operable disclosures and heading order without skipped levels");

  const example = page.getByTestId("worked-example");
  await expect(page.locator("#evidence-title")).toHaveText("Worked example from the 28 Sep study (before the signed scoring frame)");
  const caveat = page.getByTestId("worked-example-caveat");
  await expect(caveat).toBeVisible();
  await expect(caveat).toContainText("Computed on r2, which modelled 96.3% of the district (294.4 of 305.6 km²)");
  await expect(caveat).toContainText("r4, the current replay, covers 100%");
  await expect(caveat).toContainText("flood saturates at 0.25 instead of 0.20");
  await expect(caveat).toContainText("5,000-person headcount");
  await expect(caveat).toContainText("national P10/P90 anchors of the dependent share");
  await expect(caveat).toContainText("before protocol v1b was hashed");
  await expect(caveat).toContainText("must not be cited as the Mae Sai case score");
  const tiles = example.locator("dl").first().locator(":scope > div");
  await expect(tiles).toHaveCount(3);
  const chip = "Historical example · pre-D4 anchors · r2 · pre-v1b, not a protocol result";
  for (const tile of await tiles.all()) await expect(tile).toContainText(chip);
  await expect(page.getByTestId("worked-example-provenance")).toContainText("T1 scenario (model)");
  await expect(page.getByTestId("worked-example-provenance")).toContainText("replay_fpps_anchor_v1 (pre-D4)");
  await expect(example).toContainText("Class E never means safe.");
  const outsideScores = await page.evaluate(({ values }) => {
    const card = document.querySelector("[data-testid='worked-example']");
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const hits = [];
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      if (!card.contains(node) && values.some((value) => node.textContent.includes(value))) hits.push(node.textContent.trim());
    }
    return hits;
  }, { values: scores });
  assert.deepEqual(outsideScores, [], "Every score stays inside the caveated worked-example card.");
  const frame = page.getByTestId("signed-frame-table");
  await expect(frame.locator("tbody tr")).toHaveCount(5);
  assert.deepEqual(await frame.locator("tbody td[data-label='Weight']").allInnerTexts(), ["0.30", "0.25", "0.20", "0.15", "0.10"]);
  await expect(frame.locator("tbody tr").first()).toContainText("÷ 0.20");
  await expect(page.locator("#signed-frame")).toContainText("docs/decision-log-d1-d16.md");
  await expect(page.locator("#signed-frame")).toContainText("D6");
  await expect(page.locator("#signed-frame")).toContainText("D7");
  await expect(frame.locator("tbody tr").nth(2)).toContainText("Pitch level: adds DDPM located shelter (walking, 30 min).");
  await expect(page.getByTestId("replay-link")).toContainText("GISTDA’s 10 Sep flooded-area figure (about 9.9 km²) sets a stage knot, so it is a calibration anchor");
  await expect(page.getByTestId("replay-link")).toContainText("UNOSAT 3991 size check is calibration-informed, not independent (R1)");
  await expect(page.getByTestId("replay-link")).toContainText("Current replay (r4):");
  checks.push("worked example retitled, caveat before its numbers, the pre-v1b chip on every headline tile, R2 provenance, D4 table with 0.20, the five weights and the §3.4 access levels");
  await expect(page.locator("#evidence")).toContainText("3.5 m");
  await expect(page.locator("#evidence")).toContainText("12 September, 12:00 ICT");
  await expect(page.locator("#evidence")).toContainText("low confidence");
  await page.locator("#evidence summary").click();
  await expect(page.getByTestId("worked-example-rankings-caption")).toContainText(chip);
  await expect(page.getByTestId("worked-example-rankings-caption")).toContainText("Class E never means safe.");
  await expect(page.getByTestId("superseded-label-note")).toContainText("independent_magnitude_check");
  await expect(page.getByTestId("superseded-label-note")).toContainText("Since R1 (30 Sep 2026) it is calibration-informed, not independent.");
  for (const score of scores) {
    await expect(page.locator("#evidence ol")).toContainText(score);
  }
  await expect(page.locator("#evidence ol li")).toHaveCount(8);
  assert(!/53\.6|44\.0/.test(await page.locator("#evidence").innerText()), "Retired Ko Chang values must not replace the current example.");
  await expect(page.locator('#evidence a[href*="2e5a099ee075532e27236067810699ce6996c5c4"]').first()).toBeVisible();
  await expect(page.locator("#evidence")).toContainText("computes no FPPS and assigns no class (D7)");
  checks.push("pinned r2 worked example with its superseded UNOSAT label noted (R1), eight recorded scores under the same chip, and historical scenario context");

  for (const language of ["en", "th"]) {
    const thai = language === "th";
    await page.getByRole("button", { name: thai ? "ใช้ภาษาไทย" : "Use English", exact: true }).click();
    await expect(page.locator("html")).toHaveAttribute("lang", language);
    const audience = page.getByRole("group", { name: thai ? "เลือกกลุ่มผู้ใช้" : "Choose an audience" });
    for (const role of roles) {
      const button = audience.getByRole("button", { name: role[thai ? 1 : 0], exact: true });
      await button.click();
      await expect(button).toHaveAttribute("aria-pressed", "true");
      await expect(page.locator("#policy-role h3")).toHaveText(role[thai ? 3 : 2]);
      await expect(page.locator("#policy-role a")).toHaveAttribute("href", role[4]);
    }
    for (const [letter, en, th] of actions) {
      const title = thai ? th : en;
      const button = page.getByRole("button", { name: `${letter} · ${title}`, exact: true });
      await button.click();
      await expect(button).toHaveAttribute("aria-pressed", "true");
      await expect(page.locator("#policy-action h4")).toHaveText(title);
      await expect(page.locator("#policy-action p").first()).not.toBeEmpty();
      await expect(page.locator("#policy-action")).toContainText(thai ? "ผู้ทบทวนที่เสนอ" : "Suggested reviewer");
    }
    for (const summary of await page.locator("main details summary").all()) {
      if (!(await summary.evaluate((node) => node.parentElement.open))) await summary.click();
      await expect(summary.locator("..")).toHaveAttribute("open", "");
    }
    await expect(page.locator("#sources a")).toHaveCount(6);
    if (thai) {
      await expect(page.getByTestId("worked-example-caveat")).toContainText("ห้ามอ้างเป็นคะแนนของกรณีแม่สาย");
      await expect(page.getByTestId("signed-frame-table")).toContainText("ESA WorldCover คลาส 80");
      await expect(page.getByTestId("worked-example")).toContainText("ระดับ E ไม่ได้หมายความว่าปลอดภัย");
      await expect(page.getByTestId("worked-example-rankings-caption")).toContainText("ก่อน v1b ไม่ใช่ผลตามโปรโตคอล");
      await expect(page.getByTestId("replay-link")).toContainText("มีส่วนในการปรับแบบจำลอง ไม่ใช่การตรวจสอบอิสระ (R1)");
      const spaced = await page.evaluate(() => {
        const out = [];
        for (const element of document.querySelectorAll("main *")) {
          const own = [...element.childNodes].filter((node) => node.nodeType === Node.TEXT_NODE).map((node) => node.textContent).join("");
          if (!/[\u0E00-\u0E7F]/.test(own)) continue;
          const spacing = getComputedStyle(element).letterSpacing;
          if (spacing !== "normal" && parseFloat(spacing) !== 0) out.push(`${element.tagName}.${element.className}: ${spacing}`);
        }
        return out;
      });
      assert.deepEqual(spaced, [], "Thai text is never letter-spaced.");
    }
    // 701-1023 px is where the five-column components grid is narrowest, so it is sampled too.
    for (const width of widths) {
      await page.setViewportSize({ width, height: 1000 });
      await page.evaluate(() => document.fonts.ready);
      const sizes = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth, body: document.body.scrollWidth }));
      assert(sizes.document <= width + 1 && sizes.body <= width + 1, `${language} at ${width}px has overflow: ${JSON.stringify(sizes)}`);
      assert.deepEqual(await overflowingText(page), [], `${language} at ${width}px has text past its section or a clipping box`);
      if ((width === 1440 && !thai) || (width === 390 && thai)) {
        await page.evaluate(() => scrollTo(0, 0));
        await page.screenshot({ path: resolve(artifacts, `${language}-${width}-hero.png`) });
        await page.locator("#evidence").screenshot({ path: resolve(artifacts, `${language}-${width}-evidence.png`) });
        await page.locator("#priorities").screenshot({ path: resolve(artifacts, `${language}-${width}-priorities.png`) });
        await page.locator("#signed-frame").screenshot({ path: resolve(artifacts, `${language}-${width}-signed-frame.png`) });
      }
    }
    checks.push(`${language}: all audiences and A–E controls, disclosures, ${widths.length} widths (${widths.join(", ")} px) without page or text overflow${thai ? ", Thai never letter-spaced" : ""}`);
  }
  await page.reload({ waitUntil: "networkidle" });
  await expect(page.locator("html")).toHaveAttribute("lang", "th");
  await expect(page.locator("h1")).toContainText("จากหลักฐานน้ำท่วม");
  await page.getByRole("button", { name: "Use English", exact: true }).click();
  await page.reload({ waitUntil: "networkidle" });
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  checks.push("Thai and English preferences survive reload");

  for (const area of ["header", "footer"]) {
    await page.locator(`${area} a[href="/"]`).first().click();
    await expect(page.locator("[data-fg-landing]")).toBeVisible();
    await page.setViewportSize({ width: 320, height: 1000 });
    const policyLink = page.locator(`${area} a[href="/policy/"]`);
    await expect(policyLink).toBeVisible();
    if (area === "header") {
      await expect(policyLink).toBeInViewport();
      const bounds = await page.locator("header").boundingBox();
      assert(bounds && bounds.x >= 0 && bounds.x + bounds.width <= 321, "The compact landing header fits 320px.");
    }
    await policyLink.click();
    await expect(page.locator("h1")).toContainText("From flood evidence");
  }
  checks.push("landing header and footer policy links, including the 320px header, navigate both ways");

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(`${baseUrl}/policy/`, { waitUntil: "networkidle" });
  await page.locator(`[data-testid="replay-link"] a[href="${replayRoute}"]`).click();
  await expect(page.locator("h1")).toHaveText(replayTitle);
  await expect(page).toHaveURL(new RegExp(replayRoute));
  const replayPolicyLink = page.getByTestId("replay-policy-link");
  await expect(replayPolicyLink).toHaveAttribute("href", "/policy/");
  await expect(replayPolicyLink).toHaveText("How FPPS and the A–E classes work, and why this replay assigns neither");
  await replayPolicyLink.click();
  await expect(page.locator("h1")).toContainText("From flood evidence");
  checks.push("policy page links the r4 replay, and the replay footer links back to the policy page");
  await context.close();

  const offline = await browser.newContext({ viewport: { width: 390, height: 844 }, serviceWorkers: "allow" });
  const offlinePage = await offline.newPage();
  let offlineReplayVisit = false;
  recordErrors(offlinePage, () => offlineReplayVisit);
  await offlinePage.goto(`${baseUrl}/policy/`, { waitUntil: "networkidle" });
  await offlinePage.evaluate(() => navigator.serviceWorker.ready.then(() => true));
  const cachePaths = ["/", "/policy/", ...(await (await offline.request.get(`${baseUrl}/offline-assets.json`)).json())];
  await offlinePage.waitForFunction(async (paths) => {
    if (!navigator.serviceWorker.controller) return false;
    for (const key of await caches.keys()) {
      if (!key.startsWith("floodguard-offline-")) continue;
      const cache = await caches.open(key);
      if ((await Promise.all(paths.map((path) => cache.match(path)))).every(Boolean)) return true;
    }
    return false;
  }, cachePaths, { timeout: 60_000 });
  await offline.setOffline(true);
  await offlinePage.reload({ waitUntil: "networkidle" });
  await expect(offlinePage.locator("h1")).toContainText("From flood evidence");
  await offlinePage.getByRole("button", { name: "B · Keep routes open", exact: true }).click();
  await expect(offlinePage.locator("#policy-action h4")).toHaveText("Keep routes open");
  checks.push("competition cache serves the policy page and its controls offline");
  // The replay page itself is cached; its study data is saved only after an online visit, which this context never
  // made, so the replay shows its offline error state. Its footer, with the policy link, is there too.
  offlineReplayVisit = true;
  await offlinePage.locator(`[data-testid="replay-link"] a[href="${replayRoute}"]`).click();
  await expect(offlinePage.locator("h1")).toHaveText(replayTitle);
  const replayError = offlinePage.locator("main").getByRole("alert");
  await expect(replayError).toContainText("The replay data could not be loaded.");
  await expect(replayError).toContainText("You are offline and this replay's data has not been saved on this device yet.");
  await expect(offlinePage.locator("main footer")).toContainText("assigns no action class (A–E)");
  await offlinePage.getByTestId("replay-policy-link").click();
  await expect(offlinePage.locator("h1")).toContainText("From flood evidence");
  await offlinePage.waitForLoadState("networkidle");
  offlineReplayVisit = false;
  await expect(offlinePage.getByTestId("worked-example-caveat")).toBeVisible();
  checks.push("offline: the policy page opens the cached replay in its error state (only its unsaved study data fails to load), and its footer link returns to the cached policy page");
  assert.deepEqual(errors, [], "No page or console errors");
  writeFileSync(resolve(artifacts, "checks.json"), `${JSON.stringify({ checks, errors }, null, 2)}\n`);
  console.log(`policy browser smoke: ${checks.length} check groups passed; screenshots in ${artifacts}`);
} finally {
  await browser?.close();
  await new Promise((done) => server.close(done));
}
