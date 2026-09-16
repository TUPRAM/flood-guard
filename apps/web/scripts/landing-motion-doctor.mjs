// Diagnose why the landing narrative scene does or does not start.
// Usage:  node scripts/landing-motion-doctor.mjs [url] [WIDTHxHEIGHT ...]
// Reports every value the render-mode and canvas-mount branches actually read.

import { chromium } from "@playwright/test";

const url = process.argv[2]?.startsWith("http") ? process.argv[2] : "http://localhost:3000";
const sizes = (process.argv.slice(process.argv[2]?.startsWith("http") ? 3 : 2).length
  ? process.argv.slice(process.argv[2]?.startsWith("http") ? 3 : 2)
  : ["1395x595", "1395x600", "1440x780", "1920x1080"]
).map((value) => {
  const [width, height] = value.split("x").map(Number);
  return { width, height };
});

const launchArgs = ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"];
// Prefer Playwright's pinned Chromium; fall back to an installed Chrome/Edge so
// this runs without `npx playwright install`.
let browser;
for (const options of [{ headless: true, args: launchArgs }, { headless: true, args: launchArgs, channel: "chrome" }, { headless: true, args: launchArgs, channel: "msedge" }]) {
  try {
    browser = await chromium.launch(options);
    if (options.channel) console.log(`(using installed ${options.channel})\n`);
    break;
  } catch { /* try the next one */ }
}
if (!browser) {
  console.error("No browser available. Run:  npx playwright install chromium");
  process.exit(2);
}
let anyFailed = false;

for (const size of sizes) {
  const context = await browser.newContext({ viewport: size });
  const page = await context.newPage();
  const consoleErrors = [];
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  page.on("pageerror", (error) => consoleErrors.push(`pageerror: ${error.message}`));

  try {
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30_000 });
  } catch (error) {
    console.log(`${size.width}x${size.height}  UNREACHABLE  ${error.message.split("\n")[0]}`);
    console.log("  Is the dev server running?  corepack pnpm --filter @floodguard/web dev\n");
    anyFailed = true;
    await context.close();
    continue;
  }

  // Give the lazy scene a chance: scroll into the story, then wait.
  await page.evaluate(() => window.scrollTo(0, window.innerHeight * 1.2));
  await page.waitForTimeout(6000);

  const report = await page.evaluate(() => {
    const probe = document.createElement("canvas");
    const root = document.querySelector("[data-render-mode]");
    const canvas = document.querySelector("[data-story-canvas] canvas");
    const opening = document.querySelector("[data-story-opening]");
    return {
      renderMode: root?.dataset?.renderMode ?? "none",
      webgl2: !!probe.getContext("webgl2", { powerPreference: "low-power" }),
      canvasMounted: !!canvas,
      canvasSize: canvas ? [canvas.width, canvas.height] : null,
      sceneReady: document.querySelector("[data-narrative-canvas]")?.dataset?.ready ?? "n/a",
      sceneActive: document.querySelector("[data-story-canvas]")?.dataset?.sceneActive ?? "n/a",
      hidden: document.hidden,
      reducedMotion: matchMedia("(prefers-reduced-motion: reduce)").matches,
      saveData: navigator.connection?.saveData ?? false,
      openingOverflow: opening ? opening.scrollHeight - opening.clientHeight : null,
      openingHeightVar: root?.style?.getPropertyValue("--opening-height") || "(unset)",
    };
  });

  const gateOk = report.renderMode === "enhanced";
  const sceneOk = report.canvasMounted && report.sceneReady === "true";
  if (!gateOk || !sceneOk) anyFailed = true;

  console.log(`${size.width}x${size.height}`);
  console.log(`  render mode      ${report.renderMode}   ${gateOk ? "OK" : "<-- still falling back to static"}`);
  console.log(`  scene canvas     ${report.canvasMounted ? `mounted ${report.canvasSize?.join("x")}` : "NOT MOUNTED"}  ready=${report.sceneReady}  active=${report.sceneActive}`);
  console.log(`  webgl2           ${report.webgl2}`);
  console.log(`  reduced motion   ${report.reducedMotion}${report.reducedMotion ? "   <-- this alone disables the scene" : ""}`);
  console.log(`  save-data        ${report.saveData}${report.saveData ? "   <-- this alone disables the scene" : ""}`);
  console.log(`  tab hidden       ${report.hidden}`);
  console.log(`  hero overflow    ${report.openingOverflow}px   (0 = copy no longer overlaps the art)`);
  console.log(`  --opening-height ${report.openingHeightVar}   (measured at runtime)`);
  if (consoleErrors.length) {
    const notable = consoleErrors.filter((line) => !line.includes("webpack-hmr"));
    if (notable.length) console.log(`  console errors   ${notable.slice(0, 3).join(" | ")}`);
  }
  console.log("");

  await context.close();
}

await browser.close();
console.log(anyFailed ? "Some viewports did not start the scene (see above)." : "All viewports: enhanced mode and scene running.");
process.exit(anyFailed ? 1 : 0);
