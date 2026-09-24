import assert from "node:assert/strict";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

import { launchFloodGuardBrowser } from "./browser-launch.mjs";

const target = process.argv[2];
if (!target) throw new Error("Pass the Preview URL.");
const url = new URL("/", target);
assert(["http:", "https:"].includes(url.protocol), "Preview URL must use HTTP or HTTPS.");

const out = resolve("test-results/automated-gate-preview");
mkdirSync(out, { recursive: true });
const labels = {
  automated_optical_reference: "Automated optical reference (not human-qualified)",
  automated_cross_review: "Two-method automated cross-review (no human review)",
  preregistered_holdout_evaluation: "Pre-registered hold-out evaluation (automated)",
};
const expectedMarks = {
  automated_optical_reference: "true",
  automated_cross_review: "false",
  preregistered_holdout_evaluation: "true",
};
const candidates = ["mae_sai_m2_gamma0_10m_otsu_candidate", "mae_sai_20m_amplitude_comparator"];
const report = { url: url.href, checked_at_utc: new Date().toISOString(), viewports: [] };
const browser = await launchFloodGuardBrowser();
try {
  for (const width of [360, 1440]) {
    const context = await browser.newContext({ viewport: { width, height: width === 360 ? 800 : 900 }, deviceScaleFactor: 1, serviceWorkers: "block" });
    try {
      const page = await context.newPage();
      const errors = [];
      page.on("pageerror", error => errors.push(error.message));
      page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
      const response = await page.goto(url.href, { waitUntil: "domcontentloaded" });
      assert.equal(response?.status(), 200, `${width}px Preview root did not return HTTP 200`);
      await page.locator("[data-landing]").waitFor({ state: "visible" });
      const marks = {};
      for (const [id, label] of Object.entries(labels)) {
        const criterion = page.locator(`[data-criterion-id="${id}"]`);
        assert.equal(await criterion.count(), 1, `${width}px missing ${id}`);
        assert.equal(await criterion.locator("strong").textContent(), label, `${width}px ${id} label differs`);
        assert.equal(await criterion.getAttribute("data-source"), "receipt", `${width}px ${id} is not receipt-driven`);
        marks[id] = await criterion.getAttribute("data-met");
        assert.equal(marks[id], expectedMarks[id], `${width}px ${id} mark differs from the verified result`);
      }
      for (const note of [
        "Human qualification and blind review were not performed.",
        "Any final-holdout score is agreement with an automated optical map, not accuracy.",
        "Contains modified Copernicus Sentinel data 2024.",
      ]) assert(await page.getByText(note, { exact: true }).isVisible(), `${width}px missing note: ${note}`);

      const holdoutMet = await page.locator('[data-criterion-id="preregistered_holdout_evaluation"]').getAttribute("data-met") === "true";
      const scoreRows = page.locator("[data-automated-score]");
      if (holdoutMet) {
        assert.equal(await scoreRows.count(), 2, `${width}px verified holdout must show both candidates`);
        for (const id of candidates) {
          const text = await page.locator(`[data-automated-score="${id}"]`).innerText();
          assert(text.includes("agreement with an automated optical map, not accuracy"), `${width}px ${id} lacks score interpretation`);
          assert(/IoU \d+(?:\.\d+)?%|Not evaluable/.test(text), `${width}px ${id} lacks an honest score state`);
          assert(/Pre-registered limits (met|failed)\./.test(text), `${width}px ${id} lacks its limit outcome`);
        }
        const m2 = await page.locator(`[data-automated-score="${candidates[0]}"]`).innerText();
        assert(m2.includes("Not evaluable") && m2.includes("Evaluated coverage 0.0%"), `${width}px M2 abstention was not disclosed`);
        const comparator = await page.locator(`[data-automated-score="${candidates[1]}"]`).innerText();
        assert(comparator.includes("IoU 0.0%") && comparator.includes("Evaluated coverage 99.9%"), `${width}px raw comparator score differs from the frozen result`);
      } else {
        assert.equal(await scoreRows.count(), 0, `${width}px unverified holdout exposed candidate scores`);
        assert(await page.getByText("Final-holdout agreement scores are not available from a verified result.", { exact: true }).isVisible());
      }
      const documentWidth = await page.evaluate(() => document.documentElement.scrollWidth);
      assert(documentWidth <= width + 1, `${width}px page has horizontal overflow (${documentWidth}px)`);
      assert.deepEqual(errors, [], `${width}px page reported browser errors`);
      const gate = page.locator('[data-criterion-id="automated_optical_reference"]').locator("xpath=../..");
      const screenshot = resolve(out, `automated-gate-${width}.png`);
      await gate.screenshot({
        path: screenshot,
        animations: "disabled",
        style: 'main[data-landing] > header, a[href="#main-content"] { visibility: hidden !important; }',
      });
      report.viewports.push({ width, document_width: documentWidth, marks, scores: await scoreRows.count(), screenshot });
    } finally {
      await context.close();
    }
  }
  report.result = "PASS";
  console.log(JSON.stringify(report, null, 2));
} catch (error) {
  report.result = "FAIL";
  report.error = error.message;
  throw error;
} finally {
  writeFileSync(resolve(out, "report.json"), `${JSON.stringify(report, null, 2)}\n`);
  await browser.close();
}
